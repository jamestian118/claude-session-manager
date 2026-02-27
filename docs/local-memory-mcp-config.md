# CSM Local Memory 配置指南 / CSM Local Memory Configuration Guide

本方案不依赖 Graphiti 或 Docker。语义记忆由 CSM 本地 SQLite 索引提供。  
This setup does not depend on Graphiti or Docker. Semantic memory is provided by CSM local SQLite index.

---

## 中文

### 核心思路

1. CSM MCP Server 负责会话查询 + 本地 memory tool
2. `ck-search` 保留并默认启用，用于代码语义搜索
3. 本地 memory 数据库位于：
`~/Library/Application Support/claude-session-manager/memory/session-memory.db`

### MCP 配置示例

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

### 验证

```bash
python3 csm.py memory-sync --all --limit 20
python3 csm.py memory-search "handoff" --limit 5
python3 csm.py memory-status
```

---

## English

### Core Idea

1. CSM MCP Server provides session tools + local memory tools
2. `ck-search` stays enabled by default for semantic code search
3. Local memory database path:
`~/Library/Application Support/claude-session-manager/memory/session-memory.db`

### MCP Config Examples

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

### Verification

```bash
python3 csm.py memory-sync --all --limit 20
python3 csm.py memory-search "handoff" --limit 5
python3 csm.py memory-status
```
