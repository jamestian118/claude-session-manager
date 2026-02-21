# CSM + Handoff Bundle 联动改进计划

## 目标

将 CSM 升级为中心平台，通过 MCP Server 让三个 CLI（Claude Code / Codex / Gemini）都能查询旧会话上下文并接力。TUI 中按 `x` 接力时，选择目标 CLI，目标 CLI 通过 MCP 从 CSM 获取上下文。同时配置 ck 语义代码搜索作为辅助 MCP，接力后帮助 agent 快速理解代码库。

## 架构

```
三个 CLI 共享的 MCP 工具链：
┌──────────────────────────────────────────────┐
│  CSM MCP Server (stdio)                      │
│  会话管理 + 接力上下文                        │
│  search_sessions / get_session_context       │
├──────────────────────────────────────────────┤
│  Graphiti MCP Server (HTTP localhost:8000)    │
│  语义记忆 + 知识图谱（三个 CLI 共享大脑）     │
│  add_episode / search_facts / search_nodes   │
├──────────────────────────────────────────────┤
│  ck MCP Server (stdio)                       │
│  语义代码搜索（接力后辅助理解代码库）          │
│  semantic_search / hybrid_search             │
└──────────────────────────────────────────────┘
         ↑ MCP    ↑ MCP    ↑ MCP
   Claude Code / Codex / Gemini CLI
```

三层 MCP 各司其职：
- CSM: 结构化会话元数据（哪个会话、改了什么文件、跑了什么命令）
- Graphiti: 语义级知识（任务目标、决策原因、上下文关联）
- ck: 代码级理解（语义搜索代码库）

CSM 内部：
```
CSM 进程
├── MCP Server（csm mcp）    ← CLI agent 通过 MCP 调用
│   ├── search_sessions(query)
│   ├── get_session_context(session_id, tool_type)
│   ├── list_sessions(tool_filter?, limit?)
│   └── get_handoff_snapshot(session_id, tool_type)
├── TUI（csm tui）           ← 人操作，按 x 接力
└── Providers（共享，含结构化提取）
    └── Claude / Codex / Gemini
```

接力流程：
1. TUI 按 x → 选目标 CLI（1=Claude 2=Codex 3=Gemini）
2. CSM 记录待接力 session_id
3. 打开目标 CLI，prompt 告诉它通过 MCP 调用 CSM
4. CLI agent 调用 get_session_context → 拿到结构化上下文（含 files_changed/commands_run/errors）
5. 需要理解代码时，agent 通过 ck MCP 做语义搜索

## 任务分解

### Step 1: CSM 加 MCP Server 模块
- 项目: claude-session-manager
- 新增文件: `lib/mcp_server.py`
- 入口: `csm.py` 加 `mcp` 子命令
- MCP tools:
  - `list_sessions(tool_filter?, limit?)` → 返回会话列表
  - `search_sessions(query)` → 关键词搜索
  - `get_session_context(session_id, tool_type)` → 返回结构化上下文（messages, cwd, git_branch, model 等）
  - `get_handoff_snapshot(session_id, tool_type)` → 返回 handoff 快照内容（如果有）
- 依赖: mcp python SDK (`mcp`)
- 传输: stdio（标准 MCP 方式，三个 CLI 都支持）

### Step 2: TUI 接力升级
- 项目: claude-session-manager
- 修改文件: `lib/tui.py`, `lib/integration.py`
- 改动:
  - `_do_handoff()` 改为弹出目标选择菜单（1=Claude 2=Codex 3=Gemini）
  - 选择后打开目标 CLI，prompt 包含 MCP 调用指引
  - `integration.py` 的 `_open_target_tool_with_prompt()` 支持 Gemini
  - 砍掉 `r` 键（和 `o` 重复）
  - 整理状态栏按键提示

### Step 3: integration.py 支持 MCP 接力
- 项目: claude-session-manager
- 修改文件: `lib/integration.py`
- 改动:
  - 新增 `build_mcp_takeover_prompt(session_id, tool_type)` — 生成告诉 CLI 通过 MCP 获取上下文的 prompt
  - `_open_target_tool_with_prompt()` 支持 Gemini CLI
  - 保留 `build_takeover_prompt()` 作为 fallback（MCP Server 没跑时用快照文件）

### Step 4: 结构化上下文提取
- 项目: claude-session-manager
- 修改文件: `lib/models.py`, `lib/providers/claude.py`, `lib/providers/codex.py`
- 改动:
  - `SessionDetail` 新增字段: `files_changed`, `commands_run`, `errors`
  - Claude provider: 从 JSONL 的 tool_use(Edit/Write/Bash) 和 tool_result(stderr/exitCode) 中提取
  - Codex provider: 从 response_item 的 tool 输出中提取
  - MCP 的 `get_session_context` 返回这些结构化数据
- 实现方式: 纯 JSONL 解析，不需要额外 MCP 或模型调用

### Step 5: Graphiti MCP 部署 + 同步模块
- 部署: docker compose up 启动 Graphiti MCP Server（FalkorDB 默认后端）
- 新增文件: `lib/graphiti_sync.py`（CSM 内）
- 功能: 把 JSONL 会话数据通过 Graphiti MCP 的 add_episode 写入知识图谱
- 可作为 csm watch 的输出后端（daemon 监听 JSONL → 增量同步到 Graphiti）
- 三个 CLI 都配置 Graphiti MCP（HTTP transport: http://localhost:8000/mcp/）

### Step 6: ck 语义搜索 MCP 配置
- 前提: 确认 ck 已安装（cargo install ck-search）
- 三个 CLI 都加 ck MCP 配置:
  - Claude Code: ~/.claude/settings.json
  - Codex: 对应 MCP 配置
  - Gemini: ~/.gemini/settings.json
- ck 提供: semantic_search / hybrid_search / regex_search
- 用途: 接力后 agent 用 ck 快速理解代码库上下文

### Step 7: handoff-bundle repo-template 更新
- 项目: cli-handoff-bundle
- 修改文件: `repo-template/.claude/commands/`, `repo-template/.codex/commands/`
- 改动:
  - 新增 `/resume` slash command — 通过 MCP 调用 CSM 搜索旧会话并恢复上下文
  - 更新 `/takeover` — 优先走 MCP，fallback 到快照文件

### Step 8: MCP 配置文档
- 两个项目的 README 更新
- 三个 CLI 的 MCP 配置示例（CSM + Graphiti + ck 三层 MCP）

## 依赖关系

```
Step 1 (MCP Server) ← Step 2 (TUI) + Step 3 (integration) + Step 4 (结构化提取)
Step 1 + Step 3 ← Step 7 (slash commands)
Step 5 (Graphiti) 独立部署，同步模块依赖 Step 4
Step 6 (ck 配置) 独立，可与任何 step 并行
全部完成 ← Step 8 (文档)
```

Step 1 是基础，必须先完成。Step 2/3/4/5/6 可以并行。Step 7/8 最后。

## 不做的事

- 不做 watch daemon 迁入（保持 handoff-bundle 的 watch 继续运行，后续再整合）
- 不做单元测试（除非改动引入了明显的可测试模块）
