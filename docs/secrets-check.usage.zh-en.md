# scripts/secrets-check Usage (中文 + English)

## 中文

### 前置条件
- 在仓库根目录执行
- 可用 `bash` 与 `grep`

### 命令
```bash
./scripts/secrets-check
```

### 检查内容
- 启发式扫描潜在 secrets：`BEGIN PRIVATE KEY`、`AKIA...`、`xoxb-<20+>`、`xoxp-<20+>`、`ghp_<36+>`、`gho_<20+>`、`github_pat_<20+>`、`sk-<20+>`
- 默认排除：`.git/.venv/venv/node_modules/dist/build/coverage/__pycache__/.ai/.ck/docs/tests` 与 `.env.example`

### 输出与退出码
- 成功：`[secrets-check] OK`，退出码 `0`
- 失败：打印匹配项并输出 `[secrets-check] FAIL`，退出码非 `0`

## English

### Prerequisites
- Run from repository root
- `bash` and `grep` available

### Command
```bash
./scripts/secrets-check
```

### What It Checks
- Heuristic scan for potential secrets: `BEGIN PRIVATE KEY`, `AKIA...`, `xoxb-<20+>`, `xoxp-<20+>`, `ghp_<36+>`, `gho_<20+>`, `github_pat_<20+>`, `sk-<20+>`
- Default excludes: `.git/.venv/venv/node_modules/dist/build/coverage/__pycache__/.ai/.ck/docs/tests` and `.env.example`

### Output and Exit Code
- Success: `[secrets-check] OK`, exit code `0`
- Failure: prints matches and `[secrets-check] FAIL`, exits non-zero
