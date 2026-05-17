#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能说明: Claude Code hooks 单入口调度器，统一处理会话启动、负反馈采集与长期记忆管理。
版本号: 1.0.0
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import feedback_processor


def get_hooks_dir() -> Path:
    """返回 hooks 目录。"""
    return Path(__file__).resolve().parent


def get_project_dir() -> Path:
    """返回当前项目根目录。"""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir).resolve()
    return get_hooks_dir().parent.parent


def emit_json(payload: dict) -> int:
    """以 UTF-8 JSON 形式输出结果。"""
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def build_legacy_warning() -> str:
    """检测旧版 superpowers skills 目录并生成提醒。"""
    legacy_skills_dir = Path.home() / ".config" / "superpowers" / "skills"
    if legacy_skills_dir.is_dir():
        return (
            "\n\n<important-reminder>IN YOUR FIRST REPLY AFTER SEEING THIS MESSAGE YOU MUST "
            "TELL THE USER:⚠️ **WARNING:** Superpowers now uses Claude Code's skills system. "
            "Custom skills in ~/.config/superpowers/skills will not be read. Move custom skills "
            "to ~/.claude/skills instead. To make this message go away, remove "
            "~/.config/superpowers/skills</important-reminder>"
        )
    return ""


def handle_session_start() -> int:
    """生成 SessionStart 事件需要注入的上下文。"""
    warning_message = build_legacy_warning()
    session_context = (
        "<SESSION_START_REMINDER>\n"
        "Project workflow is defined by CLAUDE.md. Read CLAUDE.md first, then follow "
        ".claude/rules/MODE_ROUTER.md and the selected mode rule file. Keep startup context "
        "light. Use project-local skills only when they are explicitly relevant to the task, "
        "and do not treat using-superpowers as the primary workflow source for this repository."
        f"{warning_message}\n"
        "</SESSION_START_REMINDER>"
    )

    if os.environ.get("CURSOR_PLUGIN_ROOT"):
        return emit_json({"additional_context": session_context})

    if os.environ.get("CLAUDE_PLUGIN_ROOT") and not os.environ.get("COPILOT_CLI"):
        return emit_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": session_context,
                }
            }
        )

    return emit_json({"additionalContext": session_context})


def resolve_input_path(args: list[str]) -> tuple[Path, bool]:
    """解析输入文件路径，不存在时从标准输入临时落盘。"""
    if args:
        candidate = Path(args[0])
        if candidate.is_file():
            return candidate, False

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as temp_file:
        temp_file.write(sys.stdin.read())
        return Path(temp_file.name), True


def cleanup_temp_file(file_path: Path, should_cleanup: bool) -> None:
    """按需清理临时输入文件。"""
    if not should_cleanup:
        return
    try:
        file_path.unlink(missing_ok=True)
    except Exception:
        pass


def run_submit(args: list[str]) -> int:
    """处理 UserPromptSubmit 的负反馈采集。"""
    input_path, should_cleanup = resolve_input_path(args)
    try:
        return feedback_processor.submit(get_project_dir(), input_path)
    finally:
        cleanup_temp_file(input_path, should_cleanup)


def run_drain() -> int:
    """处理 SessionStart 时的历史反馈收敛。"""
    return feedback_processor.drain(get_project_dir())


def run_feedback_memory(args: list[str]) -> int:
    """处理长期记忆管理命令。"""
    if not args:
        print(
            "usage: hook_entry.py feedback-memory <list-pending|list-approved|list-all|approve|sync-memory> [selector]",
            file=sys.stderr,
        )
        return 1

    mode = args[0]
    forwarded_argv = ["feedback_processor.py", mode, str(get_project_dir()), *args[1:]]
    return feedback_processor.main(forwarded_argv)


def main(argv: list[str]) -> int:
    """根据子命令分发到对应 hook 逻辑。"""
    if len(argv) < 2:
        return 0

    command = argv[1]
    args = argv[2:]

    if command == "session-start":
        return handle_session_start()
    if command == "submit":
        return run_submit(args)
    if command == "drain":
        return run_drain()
    if command == "feedback-memory":
        return run_feedback_memory(args)

    print(f"unknown hook command: {command}", file=sys.stderr)
    print("supported commands: session-start, submit, drain, feedback-memory", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
