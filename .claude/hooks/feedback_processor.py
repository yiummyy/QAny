#!/usr/bin/env python3
"""Shared feedback processing for Claude Code hooks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THRESHOLD = 3
RULES_TRACKER_PATH = Path(".claude/rules_tracker.json")
FEEDBACK_DIR_PATH = Path(".claude/feedback")
MEMORY_RULES_PATH = Path(".claude/rules/FEEDBACK_MEMORY.md")
NEGATIVE_KEYWORDS = [
    "不是这样",
    "不对",
    "你又忘了",
    "我不是让你这么干",
    "错了",
    "不是这个意思",
    "应该是",
    "才对",
]
LEADING_FILLERS = [
    "请",
    "麻烦",
    "请你",
    "你",
    "应该",
    "需要",
    "要",
    "记得",
    "下次",
    "以后",
]
NORMALIZATION_RULES: list[tuple[str, str]] = [
    (r"先(?:说|给|讲|写)?(?:出)?(?:结论|答案|结果|重点)", "先给结论"),
    (r"(?:再|然后)(?:展开|说明|解释|细说|详细说明|详细展开)", "再展开"),
    (r"(?:用|请用|要用)?中文(?:回复|回答|输出)?", "中文回答"),
    (r"(?:不要|别|别再)(?:擅自|随便)?(?:删文件|删除文件)", "不要擅自删文件"),
    (r"(?:先给结论).*?(?:再展开)", "先给结论再展开"),
]
PUNCTUATION_RE = re.compile(r"[，。！？；、,:：\s]+")
SEPARATOR_RE = re.compile(r"^[，。！？；、,:：\s]+")


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def find_keyword(prompt: str) -> str | None:
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in prompt:
            return keyword
    return None


def strip_feedback_prefix(prompt: str) -> str:
    result = prompt
    changed = True
    while changed:
        changed = False
        for keyword in NEGATIVE_KEYWORDS:
            if result.startswith(keyword):
                result = result[len(keyword) :]
                result = SEPARATOR_RE.sub("", result)
                changed = True
        for filler in LEADING_FILLERS:
            if result.startswith(filler):
                result = result[len(filler) :]
                result = SEPARATOR_RE.sub("", result)
                changed = True
    return result.strip()


def canonicalize_prompt(prompt: str) -> str:
    text = normalize_text(prompt)
    text = strip_feedback_prefix(text)
    text = text.replace("`", "").replace('"', "").replace("“", "").replace("”", "")
    text = text.replace("‘", "").replace("’", "")

    compact = PUNCTUATION_RE.sub("", text)
    compact = compact.lower()

    for pattern, replacement in NORMALIZATION_RULES:
        compact = re.sub(pattern, replacement, compact)

    compact = compact.strip()
    if not compact:
        compact = normalize_text(prompt)

    if "先给结论" in compact:
        return "先给结论"
    if "中文回答" in compact:
        return "中文回答"
    if "不要擅自删文件" in compact or "不要删文件" in compact or "别删文件" in compact:
        return "不要擅自删文件"

    return compact[:120]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_rules(project_dir: Path) -> dict[str, Any]:
    return load_json(project_dir / RULES_TRACKER_PATH, {})


def save_rules(project_dir: Path, rules: dict[str, Any]) -> None:
    write_json(project_dir / RULES_TRACKER_PATH, rules)


def ensure_sentence(text: str) -> str:
    sentence = normalize_text(text).rstrip("。.!?；;")
    if not sentence:
        return ""
    return f"{sentence}。"


def memory_sentence_for_rule(entry: dict[str, Any]) -> str:
    normalized_prompt = normalize_text(entry.get("normalized_prompt", ""))
    mapping = {
        "先给结论": "回答默认先给结论，再展开说明",
        "先给结论再展开": "回答默认先给结论，再展开说明",
        "中文回答": "默认使用中文回答",
        "不要擅自删文件": "未经明确要求，不要擅自删除文件",
    }

    if normalized_prompt in mapping:
        return ensure_sentence(mapping[normalized_prompt])

    if normalized_prompt.startswith(("默认", "未经", "不要", "先", "请")):
        return ensure_sentence(normalized_prompt)

    return ensure_sentence(f"默认遵循以下长期偏好：{normalized_prompt}")


def iter_rules_by_priority(rules: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str, str]:
        rule_id, entry = item
        return (
            -int(entry.get("count", 0)),
            normalize_text(entry.get("normalized_prompt", entry.get("prompt", ""))),
            rule_id,
        )

    return sorted(rules.items(), key=sort_key)


def render_memory_markdown(approved_rules: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [
        "---",
        'description: "基于历史负反馈沉淀出的长期偏好记忆"',
        'globs: "*"',
        "---",
        "",
        "# Feedback Memory",
        "",
        "此文件由反馈处理器自动生成，用于把经批准的长期偏好作为项目规则持续提供给 Claude。",
        "",
        "## Stable Preferences",
        "",
    ]

    for _rule_id, entry in approved_rules:
        sentence = memory_sentence_for_rule(entry)
        if sentence:
            lines.append(f"- {sentence}")

    return "\n".join(lines) + "\n"


def sync_memory_file(project_dir: Path) -> tuple[int, Path]:
    rules = load_rules(project_dir)
    approved_rules = [
        (rule_id, entry)
        for rule_id, entry in iter_rules_by_priority(rules)
        if entry.get("status") == "approved"
    ]
    memory_file = project_dir / MEMORY_RULES_PATH

    if not approved_rules:
        memory_file.unlink(missing_ok=True)
        return 0, memory_file

    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text(render_memory_markdown(approved_rules), encoding="utf-8-sig")
    return len(approved_rules), memory_file


def print_rule_list(title: str, rules: list[tuple[str, dict[str, Any]]]) -> None:
    print(title)
    if not rules:
        print("- 无")
        return

    for rule_id, entry in rules:
        normalized_prompt = entry.get("normalized_prompt") or canonicalize_prompt(entry.get("prompt", ""))
        examples = entry.get("examples", [])
        example_text = f" | 示例: {examples[0]}" if examples else ""
        print(
            f"- [{entry.get('status', 'pending')}] {normalized_prompt} | count={entry.get('count', 0)} | "
            f"rule_id={rule_id[:12]}{example_text}"
        )


def select_rules(
    rules: dict[str, Any],
    selector: str,
    allowed_statuses: set[str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    needle = normalize_text(selector).lower()
    matches: list[tuple[str, dict[str, Any]]] = []

    for rule_id, entry in rules.items():
        status = entry.get("status", "pending")
        if allowed_statuses is not None and status not in allowed_statuses:
            continue

        haystacks = [
            rule_id.lower(),
            normalize_text(entry.get("normalized_prompt", "")).lower(),
            normalize_text(entry.get("prompt", "")).lower(),
        ]
        haystacks.extend(normalize_text(item).lower() for item in entry.get("examples", []))

        if any(needle and (hay == needle or hay.startswith(needle) or needle in hay) for hay in haystacks):
            matches.append((rule_id, entry))

    return matches


def resolve_rule_id(rules: dict[str, Any], normalized_prompt: str) -> str:
    preferred = hashlib.sha256(normalized_prompt.encode("utf-8")).hexdigest()
    if preferred in rules:
        return preferred

    for rule_id, entry in rules.items():
        existing_norm = entry.get("normalized_prompt")
        if not existing_norm:
            existing_norm = canonicalize_prompt(entry.get("prompt", ""))
        if existing_norm == normalized_prompt:
            return rule_id

    return preferred


def update_rule_tracker(
    rules_file: Path,
    payload: dict[str, Any],
    normalized_prompt: str,
    matched_keyword: str,
) -> tuple[int, int, str, str]:
    rules = load_json(rules_file, {})
    rule_id = resolve_rule_id(rules, normalized_prompt)
    entry = rules.get(rule_id, {})

    current_count = int(entry.get("count", 0))
    new_count = current_count + 1
    status = entry.get("status", "pending")
    if new_count >= THRESHOLD and status != "approved":
        status = "awaiting_approval"

    examples = list(entry.get("examples", []))
    raw_prompt = normalize_text(payload.get("prompt", ""))
    if raw_prompt and raw_prompt not in examples:
        examples.append(raw_prompt)
    examples = examples[-5:]

    contexts = list(entry.get("contexts", []))
    raw_context = normalize_text(payload.get("context", ""))
    if raw_context and raw_context not in contexts:
        contexts.append(raw_context)
    contexts = contexts[-3:]

    rules[rule_id] = {
        "prompt": entry.get("prompt") or raw_prompt or normalized_prompt,
        "normalized_prompt": normalized_prompt,
        "count": new_count,
        "status": status,
        "matched_keyword": matched_keyword,
        "context": entry.get("context") or raw_context,
        "examples": examples,
        "contexts": contexts,
        "last_seen_at": utc_now().isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    write_json(rules_file, rules)
    return current_count, new_count, status, rule_id


def build_hook_output(event_name: str, normalized_prompt: str, count: int) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": (
                f"用户已第 {count} 次对同一类要求给出负反馈：{normalized_prompt}。"
                "请将它视为高优先级长期偏好，后续默认按此执行；如合适，可建议写入 CLAUDE.md 或 Skills。"
            ),
        }
    }


def write_audit_record(
    feedback_dir: Path,
    payload: dict[str, Any],
    normalized_prompt: str,
    matched_keyword: str,
    rule_id: str,
    counted: bool,
) -> None:
    feedback_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")
    record = dict(payload)
    record.update(
        {
            "matched_keyword": matched_keyword,
            "normalized_prompt": normalized_prompt,
            "rule_id": rule_id,
            "counted": counted,
            "recorded_at": utc_now().isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
    )
    write_json(feedback_dir / f"{timestamp}_feedback.json", record)


def load_payload(input_path: Path) -> dict[str, Any]:
    try:
        return json.loads(input_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def submit(project_dir: Path, input_path: Path) -> int:
    payload = load_payload(input_path)
    prompt = normalize_text(payload.get("prompt", ""))
    if not prompt:
        return 0

    matched_keyword = find_keyword(prompt)
    if not matched_keyword:
        return 0

    feedback_dir = project_dir / FEEDBACK_DIR_PATH
    archive_dir = feedback_dir / "archive"
    rules_file = project_dir / RULES_TRACKER_PATH
    normalized_prompt = canonicalize_prompt(prompt)
    previous_count, new_count, _status, rule_id = update_rule_tracker(
        rules_file, payload, normalized_prompt, matched_keyword
    )
    write_audit_record(archive_dir, payload, normalized_prompt, matched_keyword, rule_id, counted=True)

    if previous_count < THRESHOLD <= new_count:
        json.dump(build_hook_output("UserPromptSubmit", normalized_prompt, new_count), sys.stdout, ensure_ascii=False)
    return 0


def process_legacy_file(rules_file: Path, file_path: Path) -> dict[str, Any] | None:
    payload = load_json(file_path, {})
    if not isinstance(payload, dict):
        file_path.unlink(missing_ok=True)
        return None

    if payload.get("counted") is True:
        return None

    prompt = normalize_text(payload.get("prompt", ""))
    matched_keyword = find_keyword(prompt)
    if not prompt or not matched_keyword:
        file_path.unlink(missing_ok=True)
        return None

    normalized_prompt = canonicalize_prompt(prompt)
    previous_count, new_count, _status, rule_id = update_rule_tracker(
        rules_file, payload, normalized_prompt, matched_keyword
    )
    payload["counted"] = True
    payload["normalized_prompt"] = normalized_prompt
    payload["rule_id"] = rule_id
    write_json(file_path, payload)
    return {
        "count": new_count,
        "crossed_threshold": previous_count < THRESHOLD <= new_count,
        "normalized_prompt": normalized_prompt,
    }


def drain(project_dir: Path) -> int:
    feedback_dir = project_dir / FEEDBACK_DIR_PATH
    rules_file = project_dir / RULES_TRACKER_PATH
    if not feedback_dir.exists():
        return 0

    notifications: list[str] = []
    for file_path in sorted(feedback_dir.glob("*.json")):
        result = process_legacy_file(rules_file, file_path)
        if result and result["crossed_threshold"]:
            notifications.append(result["normalized_prompt"])

    if notifications:
        uniq = list(dict.fromkeys(notifications))
        context = "\n".join(
            f"检测到一条来自历史反馈的长期偏好：{prompt}。请默认按此执行，并考虑写入 CLAUDE.md 或 Skills。"
            for prompt in uniq
        )
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            },
            sys.stdout,
            ensure_ascii=False,
        )
    sync_memory_file(project_dir)
    return 0


def list_rules(project_dir: Path, status_filter: str | None = None) -> int:
    rules = load_rules(project_dir)
    filtered = [
        (rule_id, entry)
        for rule_id, entry in iter_rules_by_priority(rules)
        if status_filter is None or entry.get("status") == status_filter
    ]

    if status_filter == "awaiting_approval":
        print_rule_list("待审批的长期记忆候选规则：", filtered)
    elif status_filter == "approved":
        print_rule_list("已批准并将写入长期记忆的规则：", filtered)
    else:
        print_rule_list("当前反馈规则：", filtered)
    return 0


def approve_rule(project_dir: Path, selector: str) -> int:
    rules = load_rules(project_dir)
    matches = select_rules(rules, selector, {"awaiting_approval", "approved"})

    if not matches:
        print(f"未找到可审批规则：{selector}", file=sys.stderr)
        return 1
    if len(matches) > 1:
        print("匹配到多条规则，请使用更精确的 rule_id 或规范化提示词：", file=sys.stderr)
        for rule_id, entry in matches:
            normalized_prompt = entry.get("normalized_prompt") or canonicalize_prompt(entry.get("prompt", ""))
            print(f"- {rule_id[:12]} | {normalized_prompt} | status={entry.get('status')}", file=sys.stderr)
        return 1

    rule_id, entry = matches[0]
    entry["status"] = "approved"
    entry["approved_at"] = utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")
    rules[rule_id] = entry
    save_rules(project_dir, rules)
    approved_count, memory_file = sync_memory_file(project_dir)

    print(f"已批准规则：{entry.get('normalized_prompt') or canonicalize_prompt(entry.get('prompt', ''))}")
    print(f"rule_id: {rule_id}")
    print(f"长期记忆文件: {memory_file}")
    print(f"已同步批准规则数: {approved_count}")
    return 0


def sync_memory(project_dir: Path) -> int:
    approved_count, memory_file = sync_memory_file(project_dir)
    if approved_count == 0:
        print(f"当前没有已批准规则，已清理长期记忆文件：{memory_file}")
    else:
        print(f"已同步 {approved_count} 条已批准规则到：{memory_file}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0

    mode = argv[1]
    project_dir = Path(argv[2])
    input_path = Path(argv[3]) if len(argv) > 3 else None

    if mode == "submit" and input_path is not None:
        return submit(project_dir, input_path)
    if mode == "drain":
        return drain(project_dir)
    if mode == "list-pending":
        return list_rules(project_dir, "awaiting_approval")
    if mode == "list-approved":
        return list_rules(project_dir, "approved")
    if mode == "list-all":
        return list_rules(project_dir)
    if mode == "approve" and input_path is not None:
        return approve_rule(project_dir, argv[3])
    if mode == "sync-memory":
        return sync_memory(project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
