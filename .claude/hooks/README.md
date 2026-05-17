<!--
功能说明: 说明 hooks 目录的最终结构、命令入口与维护方式。
版本号: 1.0.0
-->

# Hooks README

## 目录目标

此目录用于承载 Claude Code / Cursor 的 Hook 入口，并将不同平台的调用统一收敛到一套实现上。

当前设计原则：

- 只保留一个核心调度器
- 只保留必要的跨平台入口
- 业务逻辑集中在单一处理器文件
- 配置层与实现层命名保持一致

## 当前文件职责

### 核心文件

- `hook_entry.py`
  - Hook 单入口调度器
  - 对外只暴露 `session-start`、`submit`、`drain`、`feedback-memory`
- `feedback_processor.py`
  - 反馈规则统计、审批、长期记忆同步的核心实现

### 平台入口

- `hook-entry`
  - 类 Unix 环境入口
  - 负责定位 Python 并转发到 `hook_entry.py`
- `run-hook.cmd`
  - Windows 环境入口
  - 负责定位 Python 并转发到 `hook_entry.py`

### 平台配置

- `hooks.json`
  - Claude Code 使用的 Hook 配置
- `hooks-cursor.json`
  - Cursor 使用的 Hook 配置

## 对外命令

### 1. `session-start`

用途：

- 在会话启动时注入轻量提示
- 明确以 `CLAUDE.md` 和 `.claude/rules/*` 作为项目主规则入口
- 不再注入整份 `using-superpowers` 文本，避免与项目规则重复

调用方：

- `hooks.json`
- `hooks-cursor.json`

### 2. `submit`

用途：

- 处理 `UserPromptSubmit` 事件
- 从输入中提取用户负反馈并写入规则追踪器

调用方：

- `.claude/settings.json`

### 3. `drain`

用途：

- 处理 `SessionStart` 时的历史反馈收敛
- 将已达阈值或已批准规则同步到长期记忆

调用方：

- `.claude/settings.json`

### 4. `feedback-memory`

用途：

- 管理长期记忆相关子命令

支持子命令：

- `list-pending`
- `list-approved`
- `list-all`
- `approve <selector>`
- `sync-memory`

调用示例：

```bash
bash .claude/hooks/hook-entry feedback-memory list-all
```

```powershell
.\.claude\hooks\run-hook.cmd feedback-memory list-all
```

## 典型调用链

### Claude Code 会话启动

1. Claude Code 读取 `hooks.json`
2. 调用 `run-hook.cmd session-start`
3. `run-hook.cmd` 转发到 `hook_entry.py`
4. `hook_entry.py` 输出会话注入上下文

### 项目级反馈收敛

1. Claude Code 读取 `.claude/settings.json`
2. 在 `SessionStart` 时调用 `run-hook.cmd drain`
3. `hook_entry.py` 调用 `feedback_processor.drain()`

### 用户负反馈采集

1. Claude Code 读取 `.claude/settings.json`
2. 在 `UserPromptSubmit` 时调用 `run-hook.cmd submit`
3. `hook_entry.py` 调用 `feedback_processor.submit()`

## 维护约定

- 不要再新增 `detect-feedback`、`evolution-runner`、`session-start` 这类薄包装脚本
- 新的 Hook 能并入 `hook_entry.py` 时，优先并入，不要再拆出独立壳文件
- 若只是扩展反馈规则逻辑，优先修改 `feedback_processor.py`
- 若只是修改平台触发条件，优先修改 `hooks.json`、`hooks-cursor.json` 或 `.claude/settings.json`

## 修改建议

遇到问题时，按下面顺序排查：

1. 先看平台配置是否指向正确命令
2. 再看 `run-hook.cmd` 或 `hook-entry` 是否成功找到 Python
3. 再看 `hook_entry.py` 是否把命令分发到正确处理函数
4. 最后再排查 `feedback_processor.py` 的业务逻辑

## 当前最终结构

推荐长期保持以下最小集合：

- `README.md`
- `hook_entry.py`
- `hook-entry`
- `run-hook.cmd`
- `feedback_processor.py`
- `hooks.json`
- `hooks-cursor.json`
