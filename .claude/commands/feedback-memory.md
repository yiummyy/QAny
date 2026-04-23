# /feedback-memory

管理当前项目基于历史负反馈沉淀出的长期记忆。

## 用法

1. 查看待审批规则：
   - 运行 `".claude/hooks/run-hook.cmd" feedback-memory list-pending`
   - 或运行 `bash .claude/hooks/hook-entry feedback-memory list-pending`
2. 查看已批准规则：
   - 运行 `".claude/hooks/run-hook.cmd" feedback-memory list-approved`
   - 或运行 `bash .claude/hooks/hook-entry feedback-memory list-approved`
3. 批准某条规则：
   - 运行 `".claude/hooks/run-hook.cmd" feedback-memory approve <rule_id前缀或规范化提示词>`
   - 或运行 `bash .claude/hooks/hook-entry feedback-memory approve <rule_id前缀或规范化提示词>`
4. 手动重建长期记忆文件：
   - 运行 `".claude/hooks/run-hook.cmd" feedback-memory sync-memory`
   - 或运行 `bash .claude/hooks/hook-entry feedback-memory sync-memory`

## 行为要求

- 在执行 `approve` 前，先向用户展示待审批规则摘要并确认目标。
- 成功批准后，检查 `.claude/rules/FEEDBACK_MEMORY.md` 是否已更新。
- 如果匹配到多条规则，不要猜测，改为让用户指定更精确的 `rule_id`。
