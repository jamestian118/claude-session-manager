"""把 CSM 会话数据同步到 Graphiti MCP Server（Streamable HTTP transport）。"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

from . import store
from .models import ToolType

GRAPHITI_MCP_URL = "http://localhost:8000/mcp"

_TOOL_MAP = {
    "claude": ToolType.CLAUDE,
    "codex": ToolType.CODEX,
    "gemini": ToolType.GEMINI,
}

_session_id: str | None = None


def _mcp_post(payload: dict, timeout: int = 60) -> dict:
    """发送 MCP Streamable HTTP 请求，解析 SSE 响应。"""
    global _session_id
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session_id:
        headers["Mcp-Session-Id"] = _session_id

    req = urllib.request.Request(GRAPHITI_MCP_URL, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            _session_id = sid
        body = resp.read().decode()

    # SSE 格式: "data: {...}"
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(body) if body.strip() else {}


def _ensure_initialized():
    """确保 MCP session 已初始化。"""
    global _session_id
    if _session_id:
        return
    _mcp_post({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "csm-graphiti-sync", "version": "0.1"},
        },
    })
    _mcp_post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def _call_tool(name: str, arguments: dict) -> dict:
    """调用 Graphiti MCP tool。"""
    _ensure_initialized()
    return _mcp_post({
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }, timeout=120)


def _build_episode_content(detail) -> str:
    """从 SessionDetail 构造 episode 文本。"""
    parts = [f"工具: {detail.tool_type.label}", f"项目: {detail.project}"]
    if detail.cwd:
        parts.append(f"工作目录: {detail.cwd}")
    if detail.git_branch:
        parts.append(f"Git 分支: {detail.git_branch}")
    if detail.custom_name:
        parts.append(f"会话名称: {detail.custom_name}")
    for m in detail.messages[-10:]:
        parts.append(f"[{m.role}] {m.content[:500]}")
    if detail.files_changed:
        parts.append(f"修改文件: {', '.join(detail.files_changed[:20])}")
    if detail.commands_run:
        parts.append(f"执行命令: {', '.join(detail.commands_run[:10])}")
    if detail.errors:
        parts.append(f"错误: {', '.join(detail.errors[:5])}")
    return "\n".join(parts)


def sync_session(session_id: str, tool_type_str: str) -> dict:
    """同步单个会话到 Graphiti。"""
    tt = _TOOL_MAP.get(tool_type_str.lower())
    if not tt:
        return {"error": f"未知工具类型: {tool_type_str}"}
    detail = store.load_session_detail(session_id, tt)
    if not detail:
        return {"error": f"找不到会话: {session_id}"}
    content = _build_episode_content(detail)
    now = datetime.now(timezone.utc).isoformat()
    try:
        return _call_tool("add_memory", {
            "name": detail.custom_name or f"{detail.tool_type.label} session {session_id[:8]}",
            "episode_body": content,
            "source_description": f"CSM session {session_id} ({detail.tool_type.label})",
            "reference_time": now,
        })
    except (urllib.error.URLError, OSError) as e:
        return {"error": f"连接 Graphiti MCP 失败: {e}"}
    except Exception as e:
        return {"error": f"同步失败: {e}"}


def sync_all_recent(limit: int = 20) -> list[dict]:
    """批量同步最近的会话。"""
    sessions = store.load_sessions()[:limit]
    results = []
    for s in sessions:
        tool_str = {ToolType.CLAUDE: "claude", ToolType.CODEX: "codex", ToolType.GEMINI: "gemini"}[s.tool_type]
        r = sync_session(s.session_id, tool_str)
        results.append({"session_id": s.session_id, "tool": s.tool_type.label, "result": r})
    return results
