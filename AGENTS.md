# Project Agent Defaults (claude-session-manager)

## Start Order
- 先读 `.ai/handoff.md`（动态进度单一真相源）。
- 再读 `AGENTS.md`（长期规则）。
- 任何改动都要先给出 Goal/DoD 与验证命令。

## Policy Stack
- 进入本仓库后先执行 strict 入口（与全局一致）：
  - `/Users/Zhuanz/Documents/Code/universal-harness-kit/scripts/agent-policy-stack --tool codex --cwd "$PWD" --strict --strict-profile harness`
- 执行顺序固定：`Global -> Workflow -> Copy-to-project`。
- strict 结果若含 `fail` 不得跳过，先修复再继续。

## Verification
- Fast: `scripts/verify`
- Manual smoke: `python3 csm.py --help`

## Handoff Hygiene
- 里程碑后更新 `.ai/handoff.md`：Repo State、关键证据、Next Steps。
