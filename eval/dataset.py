"""标注数据集 v2 — 扩展 relevance_judgments + ground_truth_answer 的加载与校验."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass
class EvalItemV2:
    """单条评测用例（v2 扩展格式）."""

    id: str
    scene: str
    question: str
    expected_answer_keywords: list[str] = field(default_factory=list)
    relevant_doc_ids: list[str] = field(default_factory=list)
    min_sources: int = 1

    # ── v2 新增字段 ──────────────────────────────────
    relevance_judgments: dict[str, int] = field(default_factory=dict)
    # chunk_id → relevance_score 映射 (0=无关 1=弱相关 2=相关 3=高度相关)

    ground_truth_answer: str = ""
    # 人工标注的标准答案

    must_contain: list[str] = field(default_factory=list)
    # 答案必须包含的关键事实

    must_not_contain: list[str] = field(default_factory=list)
    # 答案禁止包含的内容

    index: str = ""
    # 指定搜索索引（空则用 Agent 默认）


def load_eval_set(path: str | Path) -> list[EvalItemV2]:
    """从 JSON 文件加载评测集."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_parse_item(obj) for obj in raw["items"]]


def _parse_item(obj: dict[str, Any]) -> EvalItemV2:
    return EvalItemV2(
        id=obj["id"],
        scene=obj.get("scene", "policy"),
        question=obj["question"],
        expected_answer_keywords=obj.get("expected_answer_keywords", []),
        relevant_doc_ids=obj.get("relevant_doc_ids", []),
        min_sources=obj.get("min_sources", 1),
        relevance_judgments=obj.get("relevance_judgments", {}),
        ground_truth_answer=obj.get("ground_truth_answer", ""),
        must_contain=obj.get("must_contain", []),
        must_not_contain=obj.get("must_not_contain", []),
        index=obj.get("index", ""),
    )


def validate_eval_set(items: list[EvalItemV2]) -> dict[str, Any]:
    """校验评测集完整性，返回缺失统计.

    用于在运行评估前快速定位标注缺口.
    """
    report = {
        "total": len(items),
        "with_relevance_judgments": 0,
        "with_ground_truth": 0,
        "with_must_contain": 0,
        "missing_relevance": cast(list[str], []),
        "missing_ground_truth": cast(list[str], []),
    }
    for item in items:
        if item.relevance_judgments:
            report["with_relevance_judgments"] += 1
        else:
            report["missing_relevance"].append(item.id)

        if item.ground_truth_answer:
            report["with_ground_truth"] += 1
        else:
            report["missing_ground_truth"].append(item.id)

        if item.must_contain:
            report["with_must_contain"] += 1

    return report
