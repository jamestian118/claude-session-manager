# scripts/install.sh + scripts/uninstall.sh Usage (中文 + English)

## 中文

### 前置条件
- 在仓库根目录执行（脚本内部会自动切到仓库根）
- 可用 `bash`
- 可用 `python3`（可用 `PYTHON_BIN` 覆盖）
- 对应 Python 具备 `pip`
- 如需自动 MCP 注册/注销，需安装目标 CLI（`claude` / `codex` / `gemini`）

### 安装脚本（install.sh）

#### 命令
```bash
./scripts/install.sh
```

#### 行为
1. 检查 `python3` 与 `python3 -m pip` 可用性
2. 执行可编辑安装：`python3 -m pip install -e <repo_root>`
3. 自动注册 CSM MCP（存在即执行，不存在则跳过）：
   - `claude mcp add -s user csm -- python3 <repo_root>/csm.py mcp`
   - `codex mcp add csm -- python3 <repo_root>/csm.py mcp`
   - `gemini mcp add -s user csm python3 <repo_root>/csm.py mcp`

### 卸载脚本（uninstall.sh）

#### 命令
```bash
./scripts/uninstall.sh
```

#### 行为
1. 自动注销 CSM MCP（存在即执行，不存在则跳过）：
   - `claude mcp remove -s user csm`
   - `codex mcp remove csm`
   - `gemini mcp remove -s user csm`
2. 清理本地状态目录：
   - 默认：`~/Library/Application Support/claude-session-manager`
   - 可通过 `CSM_STATE_DIR` 覆盖
3. 执行：`python3 -m pip uninstall -y claude-session-manager`（已安装时）

### 可选环境变量
- `PYTHON_BIN`：指定 Python 可执行文件（默认 `python3`）
- `MCP_SERVER_NAME`：MCP server 名称（默认 `csm`）
- `CSM_STATE_DIR`：仅 `uninstall.sh` 使用，覆盖状态目录

### 输出与退出码
- 成功路径会输出 `[install] ...` 或 `[uninstall] ...` 日志，并返回 `0`
- 关键步骤失败时返回非 `0`（例如 Python/pip 不可用）

### Troubleshooting
- `missing command: python3`
  - 设置可用 Python：`PYTHON_BIN=/path/to/python3 ./scripts/install.sh`
- `pip is unavailable`
  - 尝试：`python3 -m ensurepip --upgrade`
- MCP 注册失败
  - 先单独检查 CLI 命令可用性：`claude mcp --help` / `codex mcp --help` / `gemini mcp --help`
  - 脚本会继续处理其余 CLI，不会因为单个注册失败而中断

## English

### Prerequisites
- Run from the repository root (scripts will cd to repo root automatically)
- `bash` is available
- `python3` is available (`PYTHON_BIN` can override it)
- `pip` is available for the selected Python
- To auto register/unregister MCP, install target CLIs (`claude`, `codex`, `gemini`)

### Install Script (`install.sh`)

#### Command
```bash
./scripts/install.sh
```

#### Behavior
1. Validates `python3` and `python3 -m pip`
2. Installs package in editable mode: `python3 -m pip install -e <repo_root>`
3. Registers CSM MCP when each CLI is present (skips missing CLIs):
   - `claude mcp add -s user csm -- python3 <repo_root>/csm.py mcp`
   - `codex mcp add csm -- python3 <repo_root>/csm.py mcp`
   - `gemini mcp add -s user csm python3 <repo_root>/csm.py mcp`

### Uninstall Script (`uninstall.sh`)

#### Command
```bash
./scripts/uninstall.sh
```

#### Behavior
1. Unregisters CSM MCP when each CLI is present:
   - `claude mcp remove -s user csm`
   - `codex mcp remove csm`
   - `gemini mcp remove -s user csm`
2. Cleans local state directory:
   - Default: `~/Library/Application Support/claude-session-manager`
   - Override with `CSM_STATE_DIR`
3. Runs: `python3 -m pip uninstall -y claude-session-manager` (if installed)

### Optional Environment Variables
- `PYTHON_BIN`: Python executable (default: `python3`)
- `MCP_SERVER_NAME`: MCP server name (default: `csm`)
- `CSM_STATE_DIR`: uninstall-only override for state directory cleanup

### Output and Exit Codes
- Success path prints `[install] ...` or `[uninstall] ...` and exits `0`
- Hard prerequisites fail with non-zero exit code (for example missing Python/pip)

### Troubleshooting
- `missing command: python3`
  - Provide an explicit Python path: `PYTHON_BIN=/path/to/python3 ./scripts/install.sh`
- `pip is unavailable`
  - Try: `python3 -m ensurepip --upgrade`
- MCP registration failures
  - Validate CLI commands first: `claude mcp --help` / `codex mcp --help` / `gemini mcp --help`
  - Script continues with other CLIs instead of stopping on one MCP failure
