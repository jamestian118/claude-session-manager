"""CSM MCP Server — 让 CLI agent 通过 MCP 查询会话上下文并接力。"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import local_memory
from . import store
from .models import ToolType

mcp = FastMCP(
    "csm",
    instructions=(
        "CSM (CLI Session Manager) — 查询和管理 Claude Code / Codex / Gemini CLI 的会话记录，"
        "支持跨 CLI 接力，并提供本地 memory 检索。"
    ),
)


def _tool_type_from_str(s: str) -> ToolType | None:
    mapping = {"claude": ToolType.CLAUDE, "codex": ToolType.CODEX, "gemini": ToolType.GEMINI}
    return mapping.get(s.lower().strip())


def _session_to_dict(s) -> dict:
    return {
        "session_id": s.session_id,
        "tool": s.tool_type.label,
        "project": s.project,
        "first_message": s.first_display,
        "last_message": s.last_display,
        "custom_name": s.custom_name or "",
        "message_count": s.message_count,
    }


@mcp.tool(description="列出会话。可按工具筛选（claude/codex/gemini），默认返回最近 20 个。")
def list_sessions(tool_filter: str = "", limit: int = 20) -> list[dict]:
    tf = _tool_type_from_str(tool_filter) if tool_filter else None
    sessions = store.load_sessions(tf)
    return [_session_to_dict(s) for s in sessions[:limit]]


@mcp.tool(description="按关键词搜索会话（匹配名称、消息摘要、项目路径、工具名）。")
def search_sessions(query: str, limit: int = 10) -> list[dict]:
    all_sessions = store.load_sessions()
    matched = store.search_sessions(all_sessions, query)
    return [_session_to_dict(s) for s in matched[:limit]]


@mcp.tool(description="获取会话的完整上下文，用于跨 CLI 接力。返回消息历史、工作目录、git 分支、结构化提取（files_changed/commands_run/errors）等。")
def get_session_context(session_id: str, tool_type: str) -> dict:
    tt = _tool_type_from_str(tool_type)
    if not tt:
        return {"error": f"未知工具类型: {tool_type}，可选: claude/codex/gemini"}

    detail = store.load_session_detail(session_id, tt)
    if not detail:
        return {"error": f"找不到会话: {session_id}"}

    # 消息列表：只保留 user/assistant，跳过 tool/system/developer 噪声
    # 截断从 2000→1200 字符，条数从 30→20，减少 ~50% context 消耗
    msgs = [
        {"role": m.role, "content": m.content[:1200]}
        for m in detail.messages[-20:]
        if m.role in ("user", "assistant")
    ]

    result = {
        "session_id": detail.session_id,
        "tool": detail.tool_type.label,
        "project": detail.project,
        "cwd": detail.cwd,
        "git_branch": detail.git_branch,
        "model": detail.model_provider,
        "custom_name": detail.custom_name or "",
        "total_messages": len(detail.messages),
        "recent_messages": msgs,
    }

    # 结构化提取字段（Step 4 完成后会有值）
    for field in ("files_changed", "commands_run", "errors"):
        val = getattr(detail, field, None)
        if val:
            result[field] = val

    return result


@mcp.tool(description="获取会话的 handoff 快照文件内容（由 ai_handoff_watch 自动生成的 Markdown）。")
def get_handoff_snapshot(session_id: str, tool_type: str) -> dict:
    from .integration import find_handoff_snapshot
    from .models import SessionSummary

    tt = _tool_type_from_str(tool_type)
    if not tt:
        return {"error": f"未知工具类型: {tool_type}，可选: claude/codex/gemini"}

    # 构造最小 SessionSummary 用于查找快照
    dummy = SessionSummary(
        session_id=session_id, project="", first_display="",
        last_display="", timestamp_start=0, timestamp_end=0, tool_type=tt,
    )
    snap = find_handoff_snapshot(dummy)
    if not snap:
        return {"error": "找不到 handoff 快照文件"}

    try:
        content = snap.read_text(encoding="utf-8", errors="replace")
        # 截断从 15000→8000 字符，减少快照对 context window 的挤压
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (截断，共 {} 字符)".format(len(content))
        return {"path": str(snap), "content": content}
    except Exception as e:
        return {"error": f"读取快照失败: {e}"}


@mcp.tool(description="同步指定会话到本地 memory 索引（SQLite）。")
def sync_session_memory(session_id: str, tool_type: str) -> dict:
    return local_memory.sync_session(session_id, tool_type)


@mcp.tool(description="搜索本地 memory 索引（目标/决策/错误/命令等摘要）。")
def search_memory(query: str, limit: int = 10) -> list[dict]:
    return local_memory.search_memory(query, limit)


@mcp.tool(description="查看本地 memory 存储状态（路径、条目数、最近更新时间）。")
def memory_status() -> dict:
    return local_memory.get_status()
