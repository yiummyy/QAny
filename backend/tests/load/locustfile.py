"""Locust load test for Enterprise QA MVP.

Usage:
    locust -f tests/load/locustfile.py --host http://localhost:8000
    locust -f tests/load/locustfile.py --host http://localhost:8000 --headless --users 100 --run-time 5m

Requires: locust>=2.20 (pip install locust)
"""

import json
import time
from typing import Any

from locust import HttpUser, between, task


class QaUser(HttpUser):
    """Simulates user behavior: 80% Q&A, 10% upload, 10% admin."""

    wait_time = between(1, 5)
    token: str = ""
    session_counter: int = 0

    def on_start(self) -> None:
        """Login and store JWT token."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "Admin@123456"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("access_token", "")
        else:
            print(f"WARN: Login failed {resp.status_code}: {resp.text[:100]}")

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _new_session_id(self) -> str:
        self.session_counter += 1
        return f"load_{int(time.time() * 1000)}_{self.session_counter}"

    @task(8)
    def ask_question(self) -> None:
        """SSE streaming Q&A — the core workload."""
        if not self.token:
            return

        questions = [
            "公司年假制度是怎样的？",
            "如何申请报销？",
            "产品有哪些版本？",
            "忘记密码怎么办？",
            "入职需要什么材料？",
            "加班费怎么计算？",
            "系统报错500怎么处理？",
            "培训课程有哪些？",
            "出差标准是什么？",
            "如何申请调岗？",
        ]
        import random
        question = random.choice(questions)
        session_id = self._new_session_id()

        with self.client.stream(
            "POST",
            "/api/v1/qa/ask",
            json={"question": question, "session_id": session_id, "scene": "general"},
            headers=self.auth_headers,
            timeout=60,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return

            chunks: list[str] = []
            buffer = ""
            event_type = ""

            for chunk in resp.iter_content(chunk_size=4096):
                if chunk:
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.rstrip("\r")
                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            try:
                                data = json.loads(line.split(":", 1)[1].strip())
                            except (json.JSONDecodeError, IndexError):
                                continue
                            if event_type == "message":
                                chunks.append(data.get("chunk", ""))
                            elif event_type == "error":
                                resp.failure(f"SSE error: {data.get('message', 'unknown')}")

            if not chunks:
                resp.failure("No response chunks received")

    @task(1)
    def view_documents(self) -> None:
        """Admin document listing."""
        if not self.token:
            return
        resp = self.client.get(
            "/api/v1/knowledge/documents",
            params={"offset": 0, "limit": 20},
            headers=self.auth_headers,
            timeout=15,
        )
        if resp.status_code not in (200, 403):
            resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def view_metrics(self) -> None:
        """Admin metrics endpoint."""
        if not self.token:
            return
        resp = self.client.get(
            "/api/v1/admin/metrics",
            headers=self.auth_headers,
            timeout=10,
        )
        if resp.status_code not in (200, 403):
            resp.failure(f"HTTP {resp.status_code}")


class ReadOnlyUser(HttpUser):
    """Light read-only load: health checks and open endpoints."""

    wait_time = between(2, 8)
    weight = 2

    @task
    def health_check(self) -> None:
        self.client.get("/healthz", timeout=5)

    @task
    def metrics(self) -> None:
        self.client.get("/metrics", timeout=5)
