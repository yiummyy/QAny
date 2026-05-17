# /to_user_prompt

当用户输入此指令时，你的任务是**无视三次计数规则，强制将用户在指令后面输入的自定义长期偏好/规则直接写入系统的长期记忆中**。

## 触发与参数
用户将输入：`/to_user_prompt <具体的规则内容>`
例如：`/to_user_prompt 在三种模式切换遇到犹豫不决时停下来问我`

## 执行流程（你必须按顺序严格执行）

1. **获取参数**：提取用户在 `/to_user_prompt` 后面输入的全部内容，作为 `new_rule_content`。
2. **更新规则追踪器数据库**：
   - 读取项目下的 `.claude/rules_tracker.json` 文件（如果不存在则初始化为一个空对象 `{}`）。
   - 为这条新规则生成一个唯一的 `rule_id`（例如使用内容的 MD5/SHA256 或者是 `custom_rule_` 加上时间戳）。
   - 在 JSON 对象中插入或更新该条目，结构必须如下：
     ```json
     {
       "prompt": "<new_rule_content>",
       "normalized_prompt": "<new_rule_content>",
       "count": 3,
       "status": "approved",
       "matched_keyword": "force_approved_by_user"
     }
     ```
   - 将更新后的内容写回 `.claude/rules_tracker.json`。
3. **强制同步长期记忆文件**：
   - 执行终端命令以重建 Markdown 记忆文件。
   - 对于 Windows 环境，请运行：`".claude/hooks/run-hook.cmd" feedback-memory sync-memory`
   - 对于类 Unix 环境，请运行：`bash .claude/hooks/hook-entry feedback-memory sync-memory`
4. **回复确认**：
   - 向用户确认已成功将该规则（无视计数阈值）强制写入长期记忆数据库，并已同步到 `FEEDBACK_MEMORY.md`。
