# CSM — CLI Session Manager

统一管理 Claude / Codex / Gemini 的会话记录。

平台限制声明：
- `TUI` 与 `open/handoff/review` 的“新终端启动”能力按 macOS（Terminal + osascript）优化。
- 在 Linux/Windows 上，非 TUI CLI 子命令仍可用，但上述终端集成功能需要自行适配。

## 功能

- 列出、搜索、删除和恢复多种 CLI 工具的会话
- 交互式 TUI 界面（curses），支持 CJK 宽字符和中文搜索
- 按项目分组浏览会话
- 使用统计（Claude）
- Provider 可扩展架构

## 使用方法

```bash
# 启动 TUI 交互界面
python csm.py

# 列出所有会话
python csm.py list

# 搜索会话
python csm.py search <关键词>

# 恢复会话
python csm.py resume <session_id>

# 在新终端恢复会话（当前 CSM 不退出）
python csm.py open <session_id>

# 基于 handoff 快照把会话接力到另一工具（在新终端启动）
# - 默认：Claude -> Codex，Codex -> Claude
# - 你也可以显式指定目标工具
python csm.py handoff <session_id> [--to codex|claude]

# 基于 handoff 快照跳转到另一工具进行审查（review-only，新终端启动）
# - 默认：Claude -> Codex，Codex -> Claude
# - 你也可以显式指定审查工具
python csm.py review <session_id> [--to codex|claude]

# 标记会话为“已完成审查”（CSM 本地状态）
python csm.py reviewed <session_id>

# 标记会话为“已完成复查/复验”（CSM 本地状态）
python csm.py rechecked <session_id>

# 清除审查标记（可选）
python csm.py unreview <session_id>

# 修改会话名称（并尽力同步到工具自身的标题/列表）
# - 名称可以包含空格（会被自动 join）
# - 留空表示清除名称（尽力恢复工具的默认标题）
python csm.py name <session_id> <名称...>
python csm.py name <session_id>

# 删除会话
python csm.py delete <session_id>

# 查看统计
python csm.py stats

# 按工具筛选
python csm.py --tool claude list
```

说明：
- `resume` 会 `exec` 直接替换当前进程，所以你会“离开 CSM”，在当前终端进入对应 CLI。
- `open` 会用 macOS 的 Terminal（`osascript`）在**新终端窗口/Tab**里执行恢复命令，你可以继续留在 CSM 里浏览别的会话。
- `handoff` 是“跨工具接力”：它不会真正把 Codex 的 session 变成 Claude 的可 resume session（反之亦然也一样），而是依赖一个 **handoff 快照文件**，
  在新终端启动目标工具，并给它一段 takeover prompt，让它从快照继续。
- `review` 是“跨工具审查跳转”：同样依赖 **handoff 快照文件**，但会在新终端启动目标工具并注入一个严格的 reviewer 提示词：
  - 只做审查输出，不修改文件（review-only）
  - 输出固定结构的 Review 报告（Change Summary / Verification / Findings / Risk & Follow-ups）
- `reviewed` / `rechecked` / `unreview` 是“审查标记”：在 CSM 本地记录会话审查状态（P=待审，R=已审，V=已复查）。当会话处于 V 状态时，如果产生了新的对话（timestamp_end 变大），会自动重置回“未审查”。默认存储在：`~/Library/Application Support/claude-session-manager/session-flags.json`（macOS），可用 `CSM_STATE_DIR` 覆盖。
- `name` 是“会话命名”：它会保存一份 CSM 自己的自定义名称（用于 CSM 的列表/搜索/详情），并且会**尽力同步**到工具自身的数据源，让：
  - Codex：尽力同步 Codex 的 thread name（更新本地 SQLite `threads.title`）。注意：`codex resume` picker 的 `Conversation` 列是从 prompt 摘要推导的，Codex CLI 当前版本不会跟随改名。
  - `claude --resume` 的列表标题也跟着变（通过更新 Claude 的 history.jsonl 首条 display）
  - Gemini 目前不支持写回（CSM 仍可显示自定义名称）
  - 默认存储在：`~/Library/Application Support/claude-session-manager/session-names.json`（macOS）
  - 可用 `CSM_STATE_DIR` 环境变量覆盖存储目录
- 推荐用法：把 CSM 当作“可改名的 resume 列表”。尤其是 Codex 的 `codex resume` 列表不会展示改名，直接在 CSM 里按自定义名称找到会话，再用 `resume/open` 进入对应 CLI。

## TUI 快捷键

| 键 | 功能 |
|---|---|
| j/k | 上下移动 |
| Space/b | 翻页 |
| Ctrl+D/U | 半页滚动 |
| Enter | 查看详情 |
| / | 搜索（支持中文） |
| Tab | 切换工具筛选 |
| d | 删除会话 |
| r | 恢复会话（退出 CSM，替换当前终端） |
| o | 在新终端恢复会话（CSM 不退出） |
| x | 接力到另一工具（基于 handoff 快照，新终端启动） |
| v | 审查流程下一步（未审->审查；已审->复查） |
| R | 标记为已完成审查（CSM 本地状态） |
| V | 标记为已完成复查/复验（CSM 本地状态） |
| U | 清除审查标记（CSM 本地状态） |
| n | 修改会话名称（并尽力同步到工具自身标题） |
| p | 按项目分组 |
| s | 使用统计 |
| ? | 帮助 |
| q | 退出 |

### TUI 命名输入方式（修复左右移动光标 / 中文输入法问题）

在 TUI 里按 `n` 命名时，macOS 上的中文输入法（IME）在 curses 的 raw-mode 下经常会出现组合输入异常；同时也容易出现左右方向键无法编辑的问题。

CSM 提供可配置的命名输入后端（只影响 TUI 的 `n`，不影响 `python csm.py name ...`）：

- `CSM_TUI_NAME_INPUT=terminal`（默认，推荐）：临时退出 curses，用普通终端行编辑 `input()` 接收输入，支持左右移动光标，IME 表现也更稳定。
- `CSM_TUI_NAME_INPUT=dialog`：macOS 原生弹窗输入（`osascript display dialog`），IME 兼容性最好；缺点是会弹系统对话框。
- `CSM_TUI_NAME_INPUT=curses`：仍然在 curses 状态栏里编辑（支持左右/Home/End/Delete 等），但 IME 仍可能不稳定。

示例：
```bash
export CSM_TUI_NAME_INPUT=terminal  # 默认
# export CSM_TUI_NAME_INPUT=dialog
# export CSM_TUI_NAME_INPUT=curses
python csm.py
```

### 日志级别（`CSM_LOG_LEVEL`）

- 默认日志级别是 `WARNING`。
- 可设置为 `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`（也支持数值级别）。
- MCP server 会在每次 tool 请求记录日志（`tool`、`duration_ms`、`status=success|error`）；失败场景会附带 `error` 字段。

示例：
```bash
export CSM_LOG_LEVEL=INFO
python csm.py mcp
```

## 与 cli-handoff-bundle 联动（跨工具接力）

为了做到 “Claude API 挂了就立刻切 Codex 接着干” 这类场景，`handoff`/`x`/`review`/`v` 依赖一个自动生成的会话快照文件。

默认查找路径（优先级从高到低）：
- 如果会话所在目录在 git repo 内：`<repo_root>/.ai/handoff/sessions/<tool>-<session_id>.md`
- 全局快照目录（LaunchAgent 推荐位置）：
  - `~/Library/Application Support/cli-handoff-bundle/_handoff/sessions/<tool>-<session_id>.md`
- 兼容旧路径（手动运行 watcher 的默认输出）：
  - `~/Documents/Code/cli-handoff-bundle/_handoff/sessions/<tool>-<session_id>.md`

快照结构契约（与 OMO 共享）：
- `CHB_ROOT="${CHB_ROOT:-$HOME/Documents/Code/cli-handoff-bundle}"`，参考 `$CHB_ROOT/docs/snapshot-schema.md`

你也可以用环境变量覆盖/追加全局根目录（多个用 `:` 分隔）：
```bash
export CSM_HANDOFF_ROOTS="$HOME/Library/Application Support/cli-handoff-bundle/_handoff:$HOME/Documents/Code/cli-handoff-bundle/_handoff"
```

如果提示 “找不到 handoff 快照文件”，先确保 watcher 在跑：
```bash
launchctl list | rg com\\.zhuanz\\.ai-handoff-watch || true
```

或者手动生成一次（只生成快照，不常驻）：
```bash
/usr/bin/python3 "$HOME/Library/Application Support/cli-handoff-bundle/bin/ai_handoff_watch.py" once --output-mode global
```

## 二人协作审查工作流（Agent A 实现 / Agent B 审查）

推荐把“一次任务”尽量固定在一个会话（或一个分支/commit 范围）里，这样审查对象清晰可复现。

1. Agent A（实现者）完成实现 + 自测 + commit
- 建议在 repo 内运行 `/handoff` 更新 `.ai/handoff.md`（记录 commit + verify 命令 + 关键输出）
2. 在 CSM 里跳转到另一工具进行审查
- TUI：选中会话，按 `v`
- CLI：`python csm.py review <session_id>`
3. Agent B（Reviewer）只输出审查报告，不改文件
- 只读审查：不要 apply_patch，不要提交
- 输出固定结构：Change Summary / Verification / Findings / Risk & Follow-ups
4. Agent A 根据 Findings 修复 + 再验证
5. 在 CSM 里标记“已完成审查 / 已完成复查”
- 审查完成（Reviewer 侧）：
  - TUI：选中会话，按 `R`
  - CLI：`python csm.py reviewed <session_id>`
- 复查/复验完成（Implementer 侧）：
  - TUI：选中会话，按 `V`
  - CLI：`python csm.py rechecked <session_id>`

审查标记说明（仅 CSM 本地状态）：
- `P` = 待审（pending）
- `R` = 已审（reviewed，待复查）
- `V` = 已复查（rechecked）

自动重置规则：
- 当会话处于 `V` 状态时，如果产生了新的对话（timestamp_end 变大），会自动重置回“未审查”。

## MCP Server

CSM 内置 MCP Server，让 CLI agent（Claude Code / Codex / Gemini CLI）通过 MCP 协议查询会话历史、获取接力上下文。

### 启动方式

```bash
python3 csm.py mcp
```

使用 stdio transport，三个 CLI 都支持。

### MCP Tools

| Tool | 说明 |
|---|---|
| `list_sessions(tool_filter?, limit?)` | 列出会话，可按工具筛选，默认返回最近 20 个 |
| `search_sessions(query, limit?)` | 按关键词搜索会话（匹配名称、消息摘要、项目路径） |
| `get_session_context(session_id, tool_type)` | 获取完整上下文（消息历史、cwd、git branch、files_changed、commands_run、errors） |
| `get_handoff_snapshot(session_id, tool_type)` | 获取 handoff 快照文件内容（由 ai_handoff_watch 自动生成） |
| `sync_session_memory(session_id, tool_type)` | 同步指定会话到本地 memory 索引（SQLite） |
| `search_memory(query, limit?)` | 搜索本地 memory 索引（目标/决策/命令/错误摘要） |
| `memory_status()` | 查看本地 memory 存储状态（路径、条目数、最近更新时间） |

### 双层 MCP 架构（Graphiti-free）

三个 CLI 共享以下 MCP 工具链，各司其职：

```
┌──────────────────────────────────────────────┐
│  CSM MCP Server (stdio)                      │
│  会话管理 + 接力上下文 + 本地 memory          │
├──────────────────────────────────────────────┤
│  ck MCP Server (stdio)                       │
│  语义代码搜索                                 │
└──────────────────────────────────────────────┘
              ↑ MCP    ↑ MCP
   Claude Code / Codex / Gemini CLI
```

- **CSM**: 结构化会话元数据 + 本地语义记忆（SQLite）
- **ck**: 代码级理解（语义搜索代码库，默认启用）

### 三个 CLI 的 MCP 配置

#### Claude Code (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "csm": {
      "command": "python3",
      "args": ["/Users/<你的用户名>/Documents/Code/claude-session-manager/csm.py", "mcp"]
    },
    "ck-search": {
      "command": "ck",
      "args": ["mcp"]
    }
  }
}
```

#### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.csm]
command = "python3"
args = ["/Users/<你的用户名>/Documents/Code/claude-session-manager/csm.py", "mcp"]

[mcp_servers.ck-search]
command = "ck"
args = ["mcp"]
```

#### Gemini CLI (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "csm": {
      "command": "python3",
      "args": ["/Users/<你的用户名>/Documents/Code/claude-session-manager/csm.py", "mcp"]
    },
    "ck-search": {
      "command": "ck",
      "args": ["mcp"]
    }
  }
}
```

> 注意：将 `/Users/<你的用户名>/` 替换为你的实际路径。

### 本地 Memory 使用

本地 memory 不依赖 Docker，默认存储路径：
`~/Library/Application Support/claude-session-manager/memory/session-memory.db`

```bash
# 同步最近会话到本地 memory
python3 csm.py memory-sync --all --limit 20

# 搜索本地 memory
python3 csm.py memory-search "handoff" --limit 5

# 查看本地 memory 状态
python3 csm.py memory-status
```

详细配置见 `docs/local-memory-mcp-config.md`。

## 项目结构

```
csm.py              # 入口，CLI 命令
lib/
  models.py          # 数据模型（ToolType, SessionSummary, SessionDetail）
  store.py           # 数据层调度
  integration.py     # macOS Terminal / handoff 快照联动
  mcp_server.py      # MCP Server（stdio transport）
  local_memory.py    # 本地 memory 索引（SQLite）
  session_names.py   # 会话自定义名称（CSM 本地）
  session_flags.py   # 会话标记：审查状态等（CSM 本地）
  tui.py             # curses TUI 界面
  utils.py           # 共享工具函数
  providers/
    base.py          # Provider 基类
    claude.py        # Claude provider
    codex.py         # Codex provider
    gemini.py        # Gemini provider
```

## 依赖

Python 3.10+。MCP Server 需要额外安装：`pip install mcp`。  
`ck-search` 默认启用，需确保 `ck` 命令可用（例如安装 `ck-search` 并能执行 `ck mcp`）。

---

# CSM — CLI Session Manager

Unified session manager for Claude / Codex / Gemini CLI tools.

Platform limitations:
- The `TUI` and new-terminal integration (`open/handoff/review`) are optimized for macOS
  (Terminal + osascript).
- On Linux/Windows, non-TUI CLI commands remain usable, but terminal integration features
  require custom adaptation.

## Features

- List, search, delete, and resume sessions across multiple CLI tools
- Interactive TUI (curses) with CJK wide-character support and Chinese search
- Browse sessions grouped by project
- Usage statistics (Claude)
- Extensible provider architecture

## Usage

```bash
# Launch interactive TUI
python csm.py

# List all sessions
python csm.py list

# Search sessions
python csm.py search <keyword>

# Resume a session
python csm.py resume <session_id>

# Resume a session in a new Terminal (CSM stays running)
python csm.py open <session_id>

# Cross-tool handoff using a snapshot file (starts in a new Terminal)
# - Default mapping: Claude -> Codex, Codex -> Claude
python csm.py handoff <session_id> [--to codex|claude]

# Jump to another tool for a review-only pass (snapshot-based, starts in a new Terminal)
# - Default mapping: Claude -> Codex, Codex -> Claude
python csm.py review <session_id> [--to codex|claude]

# Mark a session as reviewed (CSM-local state)
python csm.py reviewed <session_id>

# Mark a session as rechecked (fixes applied + re-verified; CSM-local state)
python csm.py rechecked <session_id>

# Clear review marker (optional)
python csm.py unreview <session_id>

# Set a custom session name (and best-effort sync to the tool-native title/listing)
# - Names may contain spaces (CSM will join the remainder args)
# - No name means clear (best-effort restore of a default title)
python csm.py name <session_id> <name...>
python csm.py name <session_id>

# Delete a session
python csm.py delete <session_id>

# View statistics
python csm.py stats

# Filter by tool
python csm.py --tool claude list
```

Notes:
- `resume` uses `exec` to replace the current process, so you leave CSM and enter the target CLI in the current terminal.
- `open` uses macOS Terminal (`osascript`) to run the resume command in a new window/tab, keeping CSM usable.
- `handoff` is a cross-tool takeover: it cannot truly “resume” a Codex session inside Claude (or vice versa). Instead it finds a
  **handoff snapshot file** and starts the target tool with a short takeover prompt that points to that snapshot.
- `review` is a cross-tool review jump: it also relies on the **handoff snapshot file**, but starts the target tool with a strict reviewer prompt:
  - review-only (do not modify files)
  - output a structured Review report (Change Summary / Verification / Findings / Risk & Follow-ups)
- `reviewed` / `rechecked` / `unreview` are CSM-local markers: they store per-session review status (P=pending, R=reviewed, V=rechecked). When a session is in V state and new messages arrive (timestamp_end increases), it automatically resets back to unreviewed. Default location on macOS: `~/Library/Application Support/claude-session-manager/session-flags.json` (override with `CSM_STATE_DIR`).
- `name` stores a tool-agnostic custom name for CSM UI (list/search/detail), and also **tries to sync** it into the tool's own data so:
  - Codex: best-effort sync of Codex thread name (updates local SQLite `threads.title`). Note: the `codex resume` picker's "Conversation" column is derived from prompts in recent Codex CLI versions and may not reflect renames.
  - Claude Code: `claude --resume` list shows the new title (updates `history.jsonl` first `display`)
  - Gemini: write-back is not supported currently (CSM UI still shows the name)
  - Default location on macOS: `~/Library/Application Support/claude-session-manager/session-names.json`
  - Override the storage directory with `CSM_STATE_DIR`
- Recommended: treat CSM as your renameable resume picker. In particular, the Codex `codex resume` picker will not show renames; find sessions by custom name in CSM and then `resume/open` into the target CLI.

## TUI Shortcuts

| Key | Action |
|---|---|
| j/k | Navigate up/down |
| Space/b | Page down/up |
| Ctrl+D/U | Half-page scroll |
| Enter | View details |
| / | Search (CJK supported) |
| Tab | Cycle tool filter |
| d | Delete session |
| r | Resume session (exit CSM, replace current terminal) |
| o | Resume in new Terminal (keep CSM) |
| x | Handoff to another tool (snapshot-based, new Terminal) |
| v | Review workflow next step (unreviewed->review; reviewed->recheck) |
| R | Mark session as reviewed (CSM-local state) |
| V | Mark session as rechecked (CSM-local state) |
| U | Clear review marker (CSM-local state) |
| n | Rename session (best-effort sync) |
| p | Group by project |
| s | Usage statistics |
| ? | Help |
| q | Quit |

### TUI Rename Input Backend (Arrow Keys + Chinese IME on macOS)

When you press `n` to rename inside the TUI, macOS IME composition can be buggy under curses raw
input, and left/right cursor editing may not work reliably.

CSM provides a configurable rename input backend (only affects TUI `n`, not `python csm.py name ...`):

- `CSM_TUI_NAME_INPUT=terminal` (default, recommended): temporarily suspend curses and use normal
  terminal line editing (`input()`), so arrow keys work and IME is usually stable.
- `CSM_TUI_NAME_INPUT=dialog`: native macOS dialog (`osascript display dialog`), best IME support
  (but pops up a system dialog).
- `CSM_TUI_NAME_INPUT=curses`: inline curses editor (supports left/right/home/end/delete), but IME
  may still be unstable.

Example:
```bash
export CSM_TUI_NAME_INPUT=terminal  # default
# export CSM_TUI_NAME_INPUT=dialog
# export CSM_TUI_NAME_INPUT=curses
python csm.py
```

### Logging Level (`CSM_LOG_LEVEL`)

- Default level is `WARNING`.
- Supported values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (numeric levels also work).
- MCP server logs each tool request with `tool`, `duration_ms`, and `status=success|error`; failed requests include `error`.

Example:
```bash
export CSM_LOG_LEVEL=INFO
python csm.py mcp
```

## cli-handoff-bundle Integration (Cross-Tool Handoff)

To support “Claude API is down, switch to Codex immediately”, `handoff`/`x`/`review`/`v` relies on snapshot files generated by the watcher.

Default search order:
- Repo-local (if the session cwd is inside a git repo): `<repo_root>/.ai/handoff/sessions/<tool>-<session_id>.md`
- Global snapshot root (LaunchAgent-recommended):
  - `~/Library/Application Support/cli-handoff-bundle/_handoff/sessions/<tool>-<session_id>.md`
- Legacy/manual root:
  - `~/Documents/Code/cli-handoff-bundle/_handoff/sessions/<tool>-<session_id>.md`

Snapshot contract shared with OMO:
- `CHB_ROOT="${CHB_ROOT:-$HOME/Documents/Code/cli-handoff-bundle}"`, see `$CHB_ROOT/docs/snapshot-schema.md`

Override/extend global roots with `CSM_HANDOFF_ROOTS` (colon-separated):
```bash
export CSM_HANDOFF_ROOTS="$HOME/Library/Application Support/cli-handoff-bundle/_handoff:$HOME/Documents/Code/cli-handoff-bundle/_handoff"
```

If you get “snapshot not found”, ensure the watcher is running:
```bash
launchctl list | rg com\\.zhuanz\\.ai-handoff-watch || true
```

Or generate snapshots once (no daemon):
```bash
/usr/bin/python3 "$HOME/Library/Application Support/cli-handoff-bundle/bin/ai_handoff_watch.py" once --output-mode global
```

## Two-Agent Review Workflow (Agent A implements / Agent B reviews)

This is a practical pattern to make reviews consistent and reproducible.

1. Agent A (implementer) finishes the change, runs verification, and commits
- In a repo-first setup, update `.ai/handoff.md` (commit hash + verify commands + key outputs)
2. Jump to the reviewer tool from CSM
- TUI: select the session and press `v`
- CLI: `python csm.py review <session_id>`
3. Agent B (reviewer) is review-only
- Do not modify files, do not commit
- Output a structured Review report: Change Summary / Verification / Findings / Risk & Follow-ups
4. Agent A applies fixes and re-verifies
5. Mark the session as reviewed / rechecked in CSM
- Review done (Reviewer side):
  - TUI: press `R`
  - CLI: `python csm.py reviewed <session_id>`
- Recheck done (Implementer side):
  - TUI: press `V`
  - CLI: `python csm.py rechecked <session_id>`

Review markers (CSM-local state only):
- `P` = pending review
- `R` = reviewed (waiting for recheck)
- `V` = rechecked

Auto-reset:
- When a session is in `V` state and new messages arrive (timestamp_end increases), it resets back to unreviewed.

## MCP Server

CSM includes a built-in MCP Server that lets CLI agents (Claude Code / Codex / Gemini CLI) query session history and obtain handoff context via the MCP protocol.

### Starting the Server

```bash
python3 csm.py mcp
```

Uses stdio transport, supported by all three CLIs.

### MCP Tools

| Tool | Description |
|---|---|
| `list_sessions(tool_filter?, limit?)` | List sessions, optionally filter by tool, returns up to 20 by default |
| `search_sessions(query, limit?)` | Search sessions by keyword (matches name, message summary, project path) |
| `get_session_context(session_id, tool_type)` | Get full context (message history, cwd, git branch, files_changed, commands_run, errors) |
| `get_handoff_snapshot(session_id, tool_type)` | Get handoff snapshot file content (generated by ai_handoff_watch) |
| `sync_session_memory(session_id, tool_type)` | Sync one session into local SQLite memory index |
| `search_memory(query, limit?)` | Search local memory index (goals/decisions/commands/errors) |
| `memory_status()` | Check local memory storage status (path, entries, latest update) |

### Two-Layer MCP Architecture (Graphiti-free)

All three CLIs share the following MCP toolchain:

```
┌──────────────────────────────────────────────┐
│  CSM MCP Server (stdio)                      │
│  Session management + handoff context +      │
│  local memory index                          │
├──────────────────────────────────────────────┤
│  ck MCP Server (stdio)                       │
│  Semantic code search                        │
└──────────────────────────────────────────────┘
              ↑ MCP    ↑ MCP
   Claude Code / Codex / Gemini CLI
```

- **CSM**: Structured session metadata + local semantic memory (SQLite)
- **ck**: Code-level understanding (semantic code search, enabled by default)

### MCP Configuration for Each CLI

#### Claude Code (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "csm": {
      "command": "python3",
      "args": ["/Users/<your-username>/Documents/Code/claude-session-manager/csm.py", "mcp"]
    },
    "ck-search": {
      "command": "ck",
      "args": ["mcp"]
    }
  }
}
```

#### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.csm]
command = "python3"
args = ["/Users/<your-username>/Documents/Code/claude-session-manager/csm.py", "mcp"]

[mcp_servers.ck-search]
command = "ck"
args = ["mcp"]
```

#### Gemini CLI (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "csm": {
      "command": "python3",
      "args": ["/Users/<your-username>/Documents/Code/claude-session-manager/csm.py", "mcp"]
    },
    "ck-search": {
      "command": "ck",
      "args": ["mcp"]
    }
  }
}
```

> Note: Replace `/Users/<your-username>/` with your actual path.

### Local Memory Workflow

Local memory does not require Docker. Default storage path:
`~/Library/Application Support/claude-session-manager/memory/session-memory.db`

```bash
# Sync recent sessions into local memory
python3 csm.py memory-sync --all --limit 20

# Search local memory
python3 csm.py memory-search "handoff" --limit 5

# Check local memory status
python3 csm.py memory-status
```

## Project Structure

```
csm.py              # Entry point, CLI commands
lib/
  models.py          # Data models (ToolType, SessionSummary, SessionDetail)
  store.py           # Data layer dispatcher
  integration.py     # macOS Terminal + snapshot integration
  mcp_server.py      # MCP Server (stdio transport)
  local_memory.py    # Local memory index (SQLite)
  session_names.py   # Custom session names (CSM-local)
  session_flags.py   # Session markers (review status, etc; CSM-local)
  tui.py             # curses TUI interface
  utils.py           # Shared utility functions
  providers/
    base.py          # Provider base class
    claude.py        # Claude provider
    codex.py         # Codex provider
    gemini.py        # Gemini provider
```

## Requirements

Python 3.10+. MCP Server requires: `pip install mcp`.  
`ck-search` is enabled by default, so ensure the `ck` command is available (for example install `ck-search` and run `ck mcp`).
