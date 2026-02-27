# scripts/verify Usage (中文 + English)

## 中文

### 作用
`scripts/verify` 是本仓库的快速质量门禁，按固定顺序执行：
1. `py_compile` 静态语法检查（`csm.py`、`lib/*.py`、`lib/providers/*.py`）
2. `pytest` 测试
3. coverage 门禁（当前 scope：`lib.store`、`lib.session_flags`、`lib.utils`、`lib.local_memory`，阈值 `>=60%`）

### 前置条件
- Python 3.9+
- 已安装测试依赖：
  - `pytest`
  - `pytest-cov`

安装示例：
```bash
python3 -m pip install --user pytest pytest-cov
```

### 运行命令
```bash
./scripts/verify
```

### 输出说明
- 成功时会看到：
  - `[verify] csm py_compile OK`
  - `pytest` 汇总（通过数 + coverage 报告）
  - `[verify] pytest coverage gate OK (>=60%)`
- 失败时脚本会以非零码退出，失败点即为当前阻塞项。

### 参数/选项
`scripts/verify` 本身不接受 CLI 参数。  
如需临时调试测试，可直接手动运行 `pytest`（例如 `python3 -m pytest -q tests -k <pattern>`）。

### 常见问题
1. `No module named pytest`
   - 安装依赖：`python3 -m pip install --user pytest pytest-cov`
2. coverage 未达标
   - 查看终端里的 `term-missing` 输出，补对应模块测试后重跑。
3. 单测卡住或慢
   - 先跑子集：`python3 -m pytest -q tests/<file>.py`

## English

### Purpose
`scripts/verify` is the repo's fast quality gate. It runs in this order:
1. `py_compile` syntax checks (`csm.py`, `lib/*.py`, `lib/providers/*.py`)
2. `pytest` test suite
3. coverage gate (current scope: `lib.store`, `lib.session_flags`, `lib.utils`, `lib.local_memory`, threshold `>=60%`)

### Prerequisites
- Python 3.9+
- Test dependencies installed:
  - `pytest`
  - `pytest-cov`

Install example:
```bash
python3 -m pip install --user pytest pytest-cov
```

### Run
```bash
./scripts/verify
```

### Output
- On success:
  - `[verify] csm py_compile OK`
  - `pytest` summary (passed tests + coverage report)
  - `[verify] pytest coverage gate OK (>=60%)`
- On failure, the script exits non-zero at the blocking step.

### Flags/Options
`scripts/verify` does not take arguments.  
For focused debugging, run `pytest` directly (for example, `python3 -m pytest -q tests -k <pattern>`).

### Troubleshooting
1. `No module named pytest`
   - Install deps: `python3 -m pip install --user pytest pytest-cov`
2. Coverage below threshold
   - Use `term-missing` output to identify uncovered lines and add tests.
3. Slow/stuck tests
   - Run a subset first: `python3 -m pytest -q tests/<file>.py`
