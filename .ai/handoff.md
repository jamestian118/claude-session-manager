# CSM + Handoff Bundle 联动改进 — 接力状态

## 当前分支 & commit
- 项目1: $HOME/Documents/Code/claude-session-manager（无 git）
- 项目2: $HOME/Documents/Code/cli-handoff-bundle（无 git）

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
- 部署位置: $HOME/Documents/Code/graphiti/mcp_server/
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
- 完整计划: $HOME/Documents/Code/claude-session-manager/.ai/plan.md
