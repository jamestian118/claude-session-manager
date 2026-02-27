# Project Agent Defaults (claude-session-manager)

## Start Order
- 先读 `.ai/handoff.md`（动态进度单一真相源）。
- 再读 `AGENTS.md`（长期规则）。
- 任何改动都要先给出 Goal/DoD 与验证命令。

## Policy Stack
- 进入本仓库后先执行 strict 入口（与全局一致）：
  - `UHK_ROOT="${UHK_ROOT:-$HOME/Documents/Code/universal-harness-kit}" "$UHK_ROOT/scripts/agent-policy-stack" --tool codex --cwd "$PWD" --strict --strict-profile harness`
- 执行顺序固定：`Global -> Workflow -> Copy-to-project`。
- strict 结果若含 `fail` 不得跳过，先修复再继续。

## Repo Map
- `csm.py`：CLI 入口（命令路由、会话操作、MCP 启动）。
- `lib/providers/`：Claude/Codex/Gemini 会话源解析与适配。
- `lib/tui.py`：curses TUI 交互层。
- `lib/mcp_server.py`：MCP tools 暴露层。
- `lib/local_memory.py`：本地 SQLite memory 索引。
- `tests/`：pytest 回归套件（CLI、provider、store、memory 等）。
- `scripts/verify`：统一质量门禁入口。

## Verification
- Fast: `scripts/verify`
- Manual smoke: `python3 csm.py --help`
- Secrets: `scripts/secrets-check`

## Code Standards
- 修改 CLI 行为时同步更新 README（中文 + English）与 tests。
- 默认保持 `cmd_*` 返回码约定：`0` 成功、`1` 业务失败、`2` 参数/契约失败。
- 路径/命令优先参数化（环境变量优先，保留向后兼容默认值）。
- 只做最小必要改动；跨模块改动需在 `.ai/handoff.md` 写明影响面与回滚点。

## Testing Requirements
- 提交前至少运行：
  - `./scripts/verify`
  - `./scripts/secrets-check`
- 涉及 CLI 参数/输出变更，必须补 `tests/test_csm_cli.py` 覆盖。
- 涉及 provider/MCP 变更，至少补一条失败路径测试（异常/缺字段/兼容分支）。

## Handoff Hygiene
- 里程碑后更新 `.ai/handoff.md`：Repo State、关键证据、Next Steps。
