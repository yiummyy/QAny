"""模型质量评估 — Token F1 / Exact Match / ROUGE-L / Factual Accuracy.

通过对 LLM 生成答案与 ground_truth_answer 的多维度比对，评估模型生成质量.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from eval.dataset import EvalItemV2


# ── 分词工具 ─────────────────────────────────────────


def _jieba_tokenize(text: str) -> list[str]:
    """中文分词（尝试 jieba，不可用时 fallback 到字符级 bigram）."""
    try:
        import jieba
        return [t for t in jieba.lcut(text) if t.strip()]
    except ImportError:
        # fallback: 字符级 unigram + bigram
        chars = list(text)
        unigrams = [c for c in chars if not c.isspace()]
        bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
        return unigrams + bigrams


_PUNCT_CHARS = "，,。！？、；：""''【】《》（）()[]"
_PUNCT_TABLE = str.maketrans({c: " " for c in _PUNCT_CHARS})


def _normalize(text: str) -> str:
    """标准化文本用于 Exact Match 比较."""
    text = text.lower().strip()
    text = text.translate(_PUNCT_TABLE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── 核心指标（纯函数）───────────────────────────────────


def compute_token_f1(prediction: str, ground_truth: str) -> dict[str, float]:
    """Token-level F1（SQuAD 风格）.

    分词后计算 Precision / Recall / F1.
    """
    pred_tokens = _jieba_tokenize(prediction)
    gt_tokens = _jieba_tokenize(ground_truth)

    if not pred_tokens or not gt_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    pred_set = set(pred_tokens)
    gt_set = set(gt_tokens)
    common = pred_set & gt_set

    precision = len(common) / len(pred_set)
    recall = len(common) / len(gt_set)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def compute_exact_match(prediction: str, ground_truth: str) -> bool:
    """Exact Match：标准化后是否完全一致."""
    return _normalize(prediction) == _normalize(ground_truth)


def _lcs_len(a: list[str], b: list[str]) -> int:
    """最长公共子序列长度（DP，对短文本足够）."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            if a[i] == b[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i + 1][j], dp[i][j + 1])
    return dp[m][n]


def compute_rouge_l(prediction: str, ground_truth: str) -> float:
    """ROUGE-L：基于最长公共子序列的 F1."""
    pred_tokens = _jieba_tokenize(prediction)
    gt_tokens = _jieba_tokenize(ground_truth)

    if not pred_tokens or not gt_tokens:
        return 0.0

    lcs_len_val = _lcs_len(pred_tokens, gt_tokens)
    precision = lcs_len_val / len(pred_tokens)
    recall = lcs_len_val / len(gt_tokens)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return round(f1, 4)


def compute_factual_accuracy(
    prediction: str,
    must_contain: list[str],
    must_not_contain: list[str],
) -> dict[str, Any]:
    """事实检查：必含关键词命中率 + 禁含关键词违规数."""
    p_lower = prediction.lower()
    hits = sum(1 for kw in must_contain if kw.lower() in p_lower)
    violations = sum(1 for kw in must_not_contain if kw.lower() in p_lower)

    return {
        "must_contain_total": len(must_contain),
        "must_contain_hits": hits,
        "must_contain_hit_rate": round(hits / len(must_contain), 4) if must_contain else 1.0,
        "must_not_violations": violations,
        "passed": violations == 0 and hits == len(must_contain),
    }


# ── 评估器 ───────────────────────────────────────────


@dataclass
class QualityPerQuery:
    """单条查询的生成质量评估结果."""

    item_id: str
    answer: str = ""
    answer_short: str = ""        # 截断展示用
    f1: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    exact_match: bool = False
    rouge_l: float = 0.0
    factual_passed: bool = False
    factual_hit_rate: float = 0.0
    response_time_ms: float = 0.0
    confidence_score: float = 0.0
    status: str = "success"
    error: str = ""


@dataclass
class QualityReport:
    """模型质量评估汇总报告."""

    per_query: list[QualityPerQuery] = field(default_factory=list)
    f1_avg: float = 0.0
    em_rate: float = 0.0         # Exact Match 比例
    rouge_l_avg: float = 0.0
    factual_accuracy: float = 0.0 # 通过事实检查的比例
    total_queries: int = 0
    errors: int = 0
    by_scene: dict[str, dict[str, float]] = field(default_factory=dict)
    # scene → { f1_avg, em_rate, factual_accuracy }


class QualityEvaluator:
    """模型质量评估器 — 对完整 QA API 的答案做多维度评分."""

    def __init__(self, base_url: str = "http://localhost:8000", token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def ask_one(self, item: EvalItemV2) -> tuple[str, float, float, str]:
        """调用 QA API，返回 (answer, response_time_ms, confidence_score, error)."""
        import json as _json
        import time as _time

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                headers = {"Content-Type": "application/json"}
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"

                t_start = _time.perf_counter()
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/v1/qa/ask",
                    json={
                        "question": item.question,
                        "session_id": f"qual_{item.id}",
                        "scene": item.scene,
                    },
                    headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        return "", 0, 0, f"HTTP {resp.status_code}"

                    answer_parts: list[str] = []
                    conf_score = 0.0
                    resp_time = 0.0
                    current_event: str | None = None

                    async for raw_line in resp.aiter_lines():
                        line = raw_line.rstrip("\r")
                        if line.startswith("event: "):
                            current_event = line.split(":", 1)[1].strip()
                        elif line.startswith("data: "):
                            data_str = line.split(":", 1)[1].strip()
                            try:
                                data = _json.loads(data_str)
                            except _json.JSONDecodeError:
                                continue

                            if current_event == "message":
                                answer_parts.append(data.get("chunk", ""))
                            elif current_event == "done":
                                # DONE 事件的 full_answer 包含完整答案
                                full = data.get("full_answer", "")
                                if full:
                                    answer_parts = [full]  # 用完整答案替换拼接
                                conf_score = data.get("confidence_score", 0.0)
                                resp_time = data.get("response_time_ms", 0.0)

                    answer = "".join(answer_parts)
                    elapsed = (_time.perf_counter() - t_start) * 1000
                    return answer, resp_time or elapsed, conf_score, ""

        except httpx.TimeoutException:
            return "", 0, 0, "timeout"
        except httpx.ConnectError:
            return "", 0, 0, "connection_refused"
        except Exception as e:
            return "", 0, 0, str(e)[:200]

    async def evaluate(self, items: list[EvalItemV2]) -> QualityReport:
        """批量评估模型生成质量."""
        report = QualityReport(total_queries=len(items))
        scene_stats: dict[str, list[QualityPerQuery]] = {}

        for item in items:
            pq = QualityPerQuery(item_id=item.id)

            answer, resp_time, conf_score, error = await self.ask_one(item)

            if error:
                pq.status = "error"
                pq.error = error
                report.errors += 1
                report.per_query.append(pq)
                continue

            pq.answer = answer
            pq.answer_short = answer[:200]
            pq.response_time_ms = resp_time
            pq.confidence_score = conf_score

            # Token F1
            if item.ground_truth_answer:
                f1_result = compute_token_f1(answer, item.ground_truth_answer)
                pq.f1 = f1_result["f1"]
                pq.precision = f1_result["precision"]
                pq.recall = f1_result["recall"]
                pq.exact_match = compute_exact_match(answer, item.ground_truth_answer)
                pq.rouge_l = compute_rouge_l(answer, item.ground_truth_answer)

            # Factual Accuracy
            if item.must_contain or item.must_not_contain:
                fact = compute_factual_accuracy(answer, item.must_contain, item.must_not_contain)
                pq.factual_passed = fact["passed"]
                pq.factual_hit_rate = fact["must_contain_hit_rate"]

            report.per_query.append(pq)

            # 按场景分组
            scene_stats.setdefault(item.scene, []).append(pq)

        # 汇总
        valid = [pq for pq in report.per_query if pq.status == "success"]
        n = len(valid) or 1

        f1_vals = [pq.f1 for pq in valid if pq.f1 > 0]
        rouge_vals = [pq.rouge_l for pq in valid if pq.rouge_l > 0]
        em_hits = sum(1 for pq in valid if pq.exact_match)
        factual_hits = sum(1 for pq in valid if pq.factual_passed)

        report.f1_avg = sum(f1_vals) / len(f1_vals) if f1_vals else 0.0
        report.em_rate = round(em_hits / n, 4)
        report.rouge_l_avg = sum(rouge_vals) / len(rouge_vals) if rouge_vals else 0.0
        report.factual_accuracy = round(factual_hits / n, 4)

        for scene, pqs in scene_stats.items():
            s_valid = [pq for pq in pqs if pq.status == "success"]
            sn = len(s_valid) or 1
            sf1 = [pq.f1 for pq in s_valid if pq.f1 > 0]
            sem = sum(1 for pq in s_valid if pq.exact_match)
            sfact = sum(1 for pq in s_valid if pq.factual_passed)
            report.by_scene[scene] = {
                "f1_avg": round(sum(sf1) / len(sf1), 4) if sf1 else 0.0,
                "em_rate": round(sem / sn, 4),
                "factual_accuracy": round(sfact / sn, 4),
                "count": len(pqs),
            }

        return report
