"""Task 5: Prompt templates + renderer tests."""

from pathlib import Path

import pytest

from app.prompts.renderer import render


def test_rewrite_query_template_exists():
    path = Path(__file__).parents[2] / "app" / "prompts" / "rewrite_query.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "{query}" in content
    assert "{history}" in content


def test_generate_answer_template_exists():
    path = Path(__file__).parents[2] / "app" / "prompts" / "generate_answer.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "{query}" in content
    assert "{chunks}" in content
    assert "{permission_note}" in content


def test_hallucination_check_template_exists():
    path = Path(__file__).parents[2] / "app" / "prompts" / "hallucination_check.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "{chunks}" in content
    assert "{answer}" in content


def test_render_replaces_single_variable():
    result = render("rewrite_query", query="年假怎么申请？", history="无历史")
    assert "年假怎么申请？" in result
    assert "无历史" in result
    # Original template markers should be gone
    assert "{query}" not in result
    assert "{history}" not in result


def test_render_replaces_multiple_variables():
    result = render("generate_answer", query="测试", chunks="[S1] 参考内容", permission_note="注意权限")
    assert "测试" in result
    assert "[S1] 参考内容" in result
    assert "注意权限" in result
    assert "{query}" not in result
    assert "{chunks}" not in result
    assert "{permission_note}" not in result


def test_render_hallucination_check():
    result = render("hallucination_check", chunks="[S1] 原文", answer="答案内容")
    assert "[S1] 原文" in result
    assert "答案内容" in result
    assert "{chunks}" not in result
    assert "{answer}" not in result


def test_render_missing_variable_keeps_placeholder():
    """If a variable is not provided, the placeholder stays as-is."""
    result = render("rewrite_query", query="test")
    # history not provided, should keep the placeholder
    assert "{history}" in result


def test_render_no_extra_args_ignored():
    """Extra kwargs not present in template are silently ignored."""
    result = render("rewrite_query", query="q", history="h", extra="ignored")
    assert "q" in result
    assert "h" in result
