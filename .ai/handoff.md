# CSM + Handoff Bundle 联动改进 — 接力状态

## 当前分支 & commit
- 项目1: /Users/Zhuanz/Documents/Code/claude-session-manager（无 git）
- 项目2: /Users/Zhuanz/Documents/Code/cli-handoff-bundle（无 git）

## 全部已完成 (Step 1-8) ✅

### Step 1: CSM MCP Server ✅
- 新增 `lib/mcp_server.py` — FastMCP stdio server，4 个 tool:
  - `list_sessions(tool_filter?, limit?)`
  - `search_sessions(query, limit?)`
  - `get_session_context(session_id, tool_type)` — 返回消息历史+结构化提取
  - `get_handoff_snapshot(session_id, tool_type)` — 返回快照文件内容
- `csm.py` 加了 `mcp` 子命令，调用 `mcp.run(transport="stdio")`

### Step 2: TUI 接力升级 ✅
- `lib/tui.py` 修改:
  - `_do_handoff()` 改为弹出目标选择菜单 [1]Claude [2]Codex [3]Gemini
  - 优先用 `open_mcp_handoff_in_terminal`，fallback 到旧的 `open_handoff_in_terminal`
  - 状态栏 "x:接力" → "x:接力(选CLI)"

### Step 3: integration.py MCP 接力 + Gemini ✅
- `lib/integration.py` 修改:
  - `_open_target_tool_with_prompt()` 支持 Gemini
  - 新增 `build_mcp_takeover_prompt()` — 生成 MCP 接力 prompt
  - 新增 `open_mcp_handoff_in_terminal()` — MCP 方式接力

### Step 4: 结构化上下文提取 ✅
- `lib/models.py`: SessionDetail 新增 files_changed/commands_run/errors
- `lib/providers/claude.py`: 从 tool_use(Edit/Write/Bash) 和 tool_result 提取
- `lib/providers/codex.py`: 从 response_item 提取

### Step 5: MCP 配置 ✅
- 三个 CLI 都配好了 CSM MCP + ck MCP:
  - Claude Code: `~/.claude/settings.json` 加了 mcpServers
  - Gemini CLI: `~/.gemini/settings.json` 加了 csm + ck-search
  - Codex CLI: `~/.codex/config.toml` 加了 [mcp_servers.csm] + [mcp_servers.ck-search]
- ck 已安装: `~/.cargo/bin/ck`
- MCP Python SDK 已安装: `pip install mcp`

### Step 6: Graphiti MCP 部署 + 同步模块 ✅
- Graphiti MCP Server 已部署运行: http://localhost:8000/mcp
- FalkorDB Browser UI: http://localhost:3000/
- 部署位置: /Users/Zhuanz/Documents/Code/graphiti/mcp_server/
- 启动命令: `cd graphiti/mcp_server && docker compose -f docker/docker-compose-falkordb.yml up -d`
- `lib/graphiti_sync.py` — Streamable HTTP MCP 协议，sync_session() + sync_all_recent()
- `csm.py` 新增 `graphiti-sync` (别名 `gs`) 子命令
- 三个 CLI 已配置 Graphiti MCP（HTTP url: http://localhost:8000/mcp/）
- 端到端验证通过: 会话数据成功同步到 Graphiti 知识图谱

### Step 7: handoff-bundle repo-template 更新 ✅
- 新增 `/resume` — 三个 CLI 各一份（.claude/.codex/.gemini/commands/resume.md）
- 更新 `/takeover` — MCP 优先，fallback 到 .ai/handoff.md
- 新增 `.gemini/commands/` — takeover/handoff/closeout/resume 四个命令
- 更新 AGENTS.md + CLAUDE.md — 三 CLI 支持 + /resume + MCP 说明

### Step 8: MCP 配置文档 ✅
- CSM `README.md` — MCP Server 说明 + 三层架构图 + 配置示例 + Graphiti 部署
- handoff-bundle `README.md` — MCP 接力说明 + /resume + 配置要求

## 整体架构

```
三个 CLI 共享的 MCP 工具链：
┌──────────────────────────────────────────────┐
│  CSM MCP Server (stdio) ✅ 已完成            │
│  会话管理 + 接力上下文                        │
├──────────────────────────────────────────────┤
│  Graphiti MCP Server (HTTP) ✅ 代码就绪(待Docker)│
│  语义记忆 + 知识图谱                          │
├──────────────────────────────────────────────┤
│  ck MCP Server (stdio) ✅ 已配置              │
│  语义代码搜索                                 │
└──────────────────────────────────────────────┘
```

## 计划文件
- 完整计划: /Users/Zhuanz/Documents/Code/claude-session-manager/.ai/plan.md

## 2026-02-22 Hotfix: TUI 接力菜单闪退 + MCP tool_type 参数

### Goal / DoD
- 修复 TUI `x` 接力菜单“闪一下回主界面”的交互问题。
- 修复 MCP 接力 prompt 中 `tool_type` 参数错误，确保传 `claude|codex|gemini`。
- 保持改动最小（2 处）且通过静态校验。

### Repo State
- 路径: `/Users/Zhuanz/Documents/Code/claude-session-manager`
- 分支/commit: 非 git 工作区（无 branch/commit）
- 变更文件:
  - `lib/tui.py`
  - `lib/integration.py`

### 变更摘要
1. `lib/tui.py`
- `_do_handoff()` 选择目标 CLI 时，临时切换到阻塞输入 `timeout(-1)`，读取后用 `finally` 恢复 `timeout(100)`，避免 100ms 轮询导致菜单自动取消。

2. `lib/integration.py`
- `open_mcp_handoff_in_terminal()` 将 `build_mcp_takeover_prompt()` 的 `tool_type` 参数改为源会话 slug（`_handoff_tool_slug(session.tool_type)`），修复之前传 `target.value`（tuple）且语义错误的问题。

### 验证证据（命令 + 关键输出）
1. 语法校验
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
python3 -m py_compile csm.py lib/*.py lib/providers/*.py
```
关键输出: 无输出，退出码 0

2. MCP prompt 参数校验
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
python3 - <<'PY'
from lib.integration import build_mcp_takeover_prompt, _handoff_tool_slug
from lib.models import ToolType
for t in (ToolType.CLAUDE, ToolType.CODEX, ToolType.GEMINI):
    line = [x for x in build_mcp_takeover_prompt('sid123', _handoff_tool_slug(t)).splitlines() if 'tool_type' in x][0]
    print(t.name, '=>', line)
PY
```
关键输出:
- `CLAUDE => - tool_type: claude`
- `CODEX => - tool_type: codex`
- `GEMINI => - tool_type: gemini`

3. 代码位点核对
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
nl -ba lib/tui.py | sed -n '744,772p'
nl -ba lib/integration.py | sed -n '304,314p'
```
关键输出:
- `lib/tui.py` 出现 `self.stdscr.timeout(-1)` + `finally: self.stdscr.timeout(100)`
- `lib/integration.py` 出现 `_handoff_tool_slug(session.tool_type)`

### Next Steps
1. 手工运行 `python3 csm.py`，在列表按 `x`，确认菜单会等待输入，不再自动消失。
2. 分别选 `1/2/3` 做一次接力，检查新终端是否正常进入目标 CLI。

## 2026-02-22 Hotfix: 三 CLI 的 CSM MCP 可用性修复（依赖 + 注册源）

### Goal / DoD
- 修复 `Claude Code / Codex / Gemini CLI` 出现“未安装/断连 csm MCP server”的问题。
- DoD:
  - `python3 csm.py mcp` 可启动（不再 `ModuleNotFoundError: mcp`）。
  - `claude mcp get csm` 状态为 `Connected`。
  - `gemini mcp list` 中 `csm` 为 `Connected`。
  - `codex mcp get csm` 配置存在且启用。

### Repo State
- 路径: `/Users/Zhuanz/Documents/Code/claude-session-manager`
- 分支/commit: 非 git 工作区（无 branch/commit）
- 本次无项目源码改动；环境/配置改动:
  - Python user site-packages: 安装 `mcp==1.26.0`
  - Claude MCP 用户配置: `~/.claude.json`（新增/更新 `csm`）
  - Gemini MCP 用户配置: `~/.gemini/settings.json`（更新 `csm`）

### 变更摘要
1. 依赖修复
- `python3 -m pip install --user --break-system-packages mcp`
- 解决 `python3 csm.py mcp` 的 `ModuleNotFoundError: No module named 'mcp'`

2. Claude 注册源修复
- 使用 `claude mcp add -s user csm -- python3 /Users/Zhuanz/Documents/Code/claude-session-manager/csm.py mcp`
- 明确写入 `~/.claude.json` 用户级 MCP registry（而非仅依赖 `~/.claude/settings.json`）

3. Gemini 配置刷新
- 使用 `gemini mcp add -s user csm python3 /Users/Zhuanz/Documents/Code/claude-session-manager/csm.py mcp`
- 将 `csm` 从 `Disconnected` 修复为 `Connected`

### 验证证据（命令 + 关键输出）
1. MCP 依赖与入口
```bash
python3 -m pip show mcp
python3 /Users/Zhuanz/Documents/Code/claude-session-manager/csm.py mcp </dev/null >/tmp/csm_mcp.out 2>/tmp/csm_mcp.err; echo EXIT:$?
```
关键输出:
- `Version: 1.26.0`
- `EXIT:0`

2. Claude
```bash
claude mcp get csm
```
关键输出:
- `Scope: User config`
- `Status: ✓ Connected`

3. Gemini
```bash
gemini mcp list
```
关键输出:
- `✓ csm: python3 /Users/Zhuanz/Documents/Code/claude-session-manager/csm.py mcp (stdio) - Connected`

4. Codex
```bash
codex mcp get csm
```
关键输出:
- `enabled: true`
- `command: python3`
- `args: /Users/Zhuanz/Documents/Code/claude-session-manager/csm.py mcp`

### Next Steps
1. 分别在三端各开一条会话，实测调用一次 `csm.list_sessions` 与 `csm.get_session_context`。
2. 若后续切换 Python 主版本，重复跑一次 “四联验收” 确认 `csm` 未回归断连。

## 2026-02-23 Migration: Hard Remove Graphiti -> Local SQLite Memory

### Goal / DoD
- 移除 Graphiti 方案与相关运行依赖。
- 使用本地 SQLite memory 替代语义记忆能力。
- 保留并默认启用 `ck-search`。

### Repo State
- branch: ai/20260221-artifact-finalize (parent workspace)
- project path: /Users/Zhuanz/Documents/Code/claude-session-manager

### Changes
- 删除 Graphiti 代码与文档：
  - `lib/graphiti_sync.py`
  - `docs/graphiti-mcp-config.md`
  - `docker-compose.yml`
- 新增本地 memory 模块：
  - `lib/local_memory.py`
- 更新 CLI：
  - 新增 `memory-sync` / `memory-search` / `memory-status`
  - 移除 `graphiti-sync`
- 更新 MCP tools：
  - `sync_session_memory`
  - `search_memory`
  - `memory_status`
- 新增文档：
  - `docs/local-memory-mcp-config.md`
- README 改为双层架构（CSM + ck），并声明 Graphiti 已移除。

### Evidence
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
./scripts/verify
python3 csm.py memory-sync --all --limit 2
python3 csm.py memory-status
python3 csm.py memory-search "handoff" --limit 3
```
关键输出：
- `[verify] csm py_compile OK`
- `完成: 2/2 成功`
- `entries: 2`

### Next Steps
1. 在 Claude/Codex/Gemini 三端各调用一次 `search_memory` MCP tool 做实测。
2. 按需把旧的 Graphiti 配置块从用户级配置文件中清理（避免认知噪音）。

## 2026-02-24 Refactor: 数据安全 + 并发 + 启动性能硬化（Conductor Review Plan）

### Goal / DoD
- 修复 `delete_session` 的非原子重写风险（避免 history/global state 截断）。
- 修复 local memory 因 `content_hash` 变更导致的重复插入泄漏。
- 修复 `session_flags/session_names` 并发读改写覆盖。
- 处理编码损坏日志导致的 `UnicodeDecodeError` 风险。
- 为 provider `load_sessions` 引入基于 `st_mtime` 的缓存，减少重复全量解析。

### Repo State
- 路径: `/Users/Zhuanz/Documents/Code/claude-session-manager`
- 分支/commit: 非 git 工作区（无 branch/commit）
- 变更文件:
  - `lib/providers/claude.py`
  - `lib/providers/codex.py`
  - `lib/providers/gemini.py`
  - `lib/local_memory.py`
  - `lib/session_flags.py`
  - `lib/session_names.py`

### 变更摘要
1. 原子写入
- `ClaudeProvider.delete_session()` 和 `CodexProvider.delete_session()` 的 `history.jsonl` 重写改为 `tmp + os.replace`。
- `CodexProvider.delete_session()` 的 `.codex-global-state.json` 重写改为原子 JSON 写入。

2. SQLite 去重泄漏
- `memory_entries` 唯一约束改为 `UNIQUE(session_id, tool)`。
- `sync_session()` 改为 `ON CONFLICT(session_id, tool) DO UPDATE`。
- 增加旧 schema 自动迁移：保留每个 `(session_id, tool)` 最新记录，并保留 `memory_entries_backup_*` 备份表。

3. 并发锁
- `session_flags.py` / `session_names.py` 增加 `fcntl.flock` 文件锁（`.lock` 文件）包裹读改写循环。

4. 编码容错
- 关键读取点统一使用 `errors="replace"`（providers + state json + gemini annotation）。

5. 启动性能
- `ClaudeProvider` / `CodexProvider` 增加 `load_sessions` 缓存，基于相关输入文件的 `mtime/size` key 命中返回。

### 验证证据（命令 + 关键输出）
1. 项目 verify
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
./scripts/verify
```
关键输出:
- `[verify] csm py_compile OK`

2. 定向 smoke（upsert / 并发 state / cache）
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
python3 - <<'PY'
# 已执行: local_memory upsert + names/flags 写入 + provider cache 命中检查
PY
```
关键输出:
- `[smoke] memory_upsert inserted_flags=True,False rows=1`
- `[smoke] names_ok=True names_count=2 flags_ok=True flags_count=2`
- `[smoke] codex_cache_calls={'h': 1, 'f': 1, 's': 1}`

3. Claude cache 二次调用无重复扫描
```bash
cd /Users/Zhuanz/Documents/Code/claude-session-manager
python3 - <<'PY'
# 已执行: ClaudeProvider 两次 load_sessions 计数对比
PY
```
关键输出:
- `first=109 second=109 delta=0`

### Next Steps
1. 在真实大规模会话数据下做一次 TUI 冷启动耗时对比（before/after）。
2. 为 `local_memory` 增加回归测试（迁移幂等、冲突更新语义）。
3. 为 `session_flags/session_names` 增加多进程并发回归测试。

## 当前状态：[Phase 2 任务 2.8/2.9/2.10 已完成；关键文件为 `pyproject.toml`、`scripts/install.sh`、`scripts/uninstall.sh`、`docs/install-uninstall.usage.zh-en.md`]
## 下一步：[如需端到端演练可运行 `./scripts/install.sh` 与 `./scripts/uninstall.sh`；最小验收命令 `./scripts/verify && ./scripts/secrets-check`]
## 已知问题：[本次未执行 install/uninstall 以避免改动本机 MCP 注册与 state 目录；脚本语法与主流程已静态检查]

## 当前状态：[Phase 3 任务 3.6/3.7/3.8/3.9 已完成；关键文件为 `lib/logging_config.py`、`csm.py`、`lib/store.py`、`lib/mcp_server.py`、`lib/providers/codex.py`、`lib/tui.py`]
## 下一步：[可选运行 `CSM_LOG_LEVEL=INFO python3 csm.py mcp` 并实际调用一次 MCP tool，确认 request logging 在运行态输出；最小验收命令 `./scripts/verify && ./scripts/secrets-check`]
## 已知问题：[本次未执行真实 MCP 客户端端到端调用，仅完成静态与脚本验收；默认日志级别为 WARNING，需设置 `CSM_LOG_LEVEL` 才能看到 info/debug 级日志]

## 2026-02-27 Gate 3 收口补丁：console script

### Goal / DoD
- Goal: 让 Gate 3 命令 `csm list` 可直接执行（非 `python csm.py` 等价路径）。
- DoD: `pyproject.toml` 提供 `project.scripts.csm`，并通过 verify/secrets-check。

### Changes
- Updated: `pyproject.toml`
  - 新增：
    - `[project.scripts]`
    - `csm = "csm:main"`

### Verification
- `/Users/Zhuanz/Documents/Code/universal-harness-kit/scripts/agent-policy-stack --tool codex --cwd "$PWD" --strict --strict-profile harness`
  - `strict_result=pass`
- `./scripts/verify`
  - `[verify] csm py_compile OK`
- `./scripts/secrets-check`
  - `[secrets-check] OK`

### Commit
- `52985a8` `build: add csm console entrypoint script`

### Note
- 当前环境默认 Python 3.9 路径运行 `csm` 仍可能触发运行期类型注解兼容问题；Gate 3 实测使用 Python 3.11 wrapper 通过。
