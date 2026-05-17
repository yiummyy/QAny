"""Unit tests for citation verifier (Spec: citation-verification)."""

from app.tools.citation_verifier import (
    CITATION_VERIFIED,
    CITATION_SUSPICIOUS,
    _classify_claim,
    _detect_orphan_claims,
    _is_filler,
    _split_sentences,
    extract_anchors,
    map_anchors_to_chunks,
)


# ---------------------------------------------------------------------------
# extract_anchors
# ---------------------------------------------------------------------------


def test_extract_single_anchor():
    result = extract_anchors("公司规定年假为15天[S1]。")
    assert len(result) == 1
    assert result[0][0] == "S1"
    assert "年假" in result[0][1]
    assert result[0][1] == "公司规定年假为15天[S1]。"
    # Clean sentence: anchor removed
    assert "S1" not in result[0][2]


def test_extract_multiple_anchors():
    result = extract_anchors("报销比例为80%[S1]。超过需审批[S2]。")
    assert len(result) == 2
    assert result[0][0] == "S1"
    assert result[1][0] == "S2"


def test_extract_no_anchors():
    result = extract_anchors("这是纯文本，没有任何引用标记。")
    assert len(result) == 0


def test_extract_multi_digit_anchor():
    result = extract_anchors("参考[S10]的内容。")
    assert len(result) == 1
    assert result[0][0] == "S10"


def test_extract_multiple_anchors_in_same_sentence():
    """One sentence with two anchors: [S1] and [S3]."""
    result = extract_anchors("根据[S1]和[S3]的规定。")
    assert len(result) == 2


def test_extract_empty_text():
    result = extract_anchors("")
    assert len(result) == 0


# ---------------------------------------------------------------------------
# map_anchors_to_chunks
# ---------------------------------------------------------------------------


def test_map_basic():
    chunks = [
        {"chunk_id": "a1", "content": "A"},
        {"chunk_id": "b2", "content": "B"},
    ]
    mapping = map_anchors_to_chunks(["S1", "S2"], chunks)
    assert mapping["S1"]["chunk_id"] == "a1"
    assert mapping["S2"]["chunk_id"] == "b2"


def test_map_out_of_bounds():
    chunks = [{"chunk_id": "a1"}]
    mapping = map_anchors_to_chunks(["S99"], chunks)
    assert "S99" not in mapping


def test_map_empty_chunks():
    mapping = map_anchors_to_chunks(["S1"], [])
    assert "S1" not in mapping


# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------


def test_split_chinese():
    result = _split_sentences("第一句话。第二句话！第三句话？")
    assert len(result) == 3


def test_split_mixed():
    result = _split_sentences("Hello world. 中文断句。Another one!")
    assert len(result) == 3


def test_split_single():
    result = _split_sentences("only one")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# _is_filler
# ---------------------------------------------------------------------------


def test_filler_greeting():
    assert _is_filler("您好，有什么可以帮你的？") is True


def test_filler_welcome():
    assert _is_filler("欢迎使用本系统。") is True


def test_filler_reference():
    assert _is_filler("详见员工手册第三章。") is True


def test_not_filler():
    assert _is_filler("年假为15天。") is False


def test_not_filler_number():
    assert _is_filler("公司营收为30亿元。") is False


# ---------------------------------------------------------------------------
# _classify_claim
# ---------------------------------------------------------------------------


def test_claim_date():
    assert _classify_claim("2025年3月15日发布的政策。") == "日期"


def test_claim_number():
    assert _classify_claim("报销比例为80%。") == "数字"


def test_claim_regulation():
    assert _classify_claim("根据公司考勤管理制度。") == "规定"


def test_claim_doc_name():
    assert _classify_claim("参见《员工手册》第三章。") == "名称"


def test_claim_other():
    assert _classify_claim("建议咨询相关部门。") == "其他"


def test_claim_none():
    """Connective text without factual claim signal."""
    assert _classify_claim("因此建议用户。") == "其他"


# ---------------------------------------------------------------------------
# _detect_orphan_claims
# ---------------------------------------------------------------------------


def test_detect_no_orphans_when_all_cited():
    orphans = _detect_orphan_claims(
        "年假为15天[S1]。报销比例80%[S2]。",
        {"S1", "S2"},
    )
    assert len(orphans) == 0


def test_detect_orphan_number():
    orphans = _detect_orphan_claims(
        "年假为15天[S1]。公司营收为30亿元。",
        {"S1"},
    )
    assert len(orphans) >= 1
    assert any(o.claim_type == "数字" for o in orphans)


def test_skip_filler_in_orphan_detection():
    orphans = _detect_orphan_claims(
        "年假为15天[S1]。如需帮助请联系管理员。",
        {"S1"},
    )
    # "如需帮助请联系管理员" is filler
    assert all("如需" not in o.sentence for o in orphans)


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------


def test_thresholds():
    assert CITATION_VERIFIED == 0.75
    assert CITATION_SUSPICIOUS == 0.55
    assert CITATION_VERIFIED > CITATION_SUSPICIOUS
