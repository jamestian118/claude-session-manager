# Graphiti MCP 配置指南 / Graphiti MCP Configuration Guide

将 Graphiti MCP Server 接入各 CLI 工具的配置示例。
Configuration examples for integrating Graphiti MCP Server with each CLI tool.

前提：Graphiti MCP Server 已通过 `docker compose up -d` 启动，监听 `http://localhost:8000/mcp/`。
Prerequisite: Graphiti MCP Server is running via `docker compose up -d`, listening on `http://localhost:8000/mcp/`.

---

## Claude Code

文件路径 / File path: `~/.claude/settings.json`

```json
{
  "mcpServers": {
    "graphiti": {
      "type": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

---

## Codex

文件路径 / File path: `~/.codex/config.toml`

```toml
[mcp_servers.graphiti]
type = "http"
url = "http://localhost:8000/mcp/"
```

---

## Gemini CLI

文件路径 / File path: `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "graphiti": {
      "httpUrl": "http://localhost:8000/mcp/"
    }
  }
}
```

---

## 验证 / Verification

启动任一 CLI 后，可尝试调用 Graphiti 提供的 MCP tool（如 `search_nodes`）来验证连接是否正常。
After launching any CLI, try calling a Graphiti MCP tool (e.g. `search_nodes`) to verify the connection.
