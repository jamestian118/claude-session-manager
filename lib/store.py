"""数据层 — 聚合调度，统一管理多工具会话"""

from collections import defaultdict

from . import session_flags
from . import session_names
from .models import SessionDetail, SessionSummary, ToolType
from .providers.base import BaseProvider
from .providers.claude import ClaudeProvider
from .providers.codex import CodexProvider
from .providers.gemini import GeminiProvider

# 所有已注册的 provider
_PROVIDERS: list[BaseProvider] = [
    ClaudeProvider(),
    CodexProvider(),
    GeminiProvider(),
]


def get_available_providers() -> list[BaseProvider]:
    """返回数据目录存在的 provider"""
    return [p for p in _PROVIDERS if p.is_available()]


def _get_provider(tool_type: ToolType) -> BaseProvider | None:
    for p in _PROVIDERS:
        if p.tool_type == tool_type:
            return p
    return None


# ── 会话列表 ──


def load_sessions(tool_filter: ToolType | None = None) -> list[SessionSummary]:
    """合并所有可用 provider 的会话，按时间倒序"""

    providers = get_available_providers()
    if tool_filter:
        providers = [p for p in providers if p.tool_type == tool_filter]

    all_sessions: list[SessionSummary] = []
    for p in providers:
        try:
            all_sessions.extend(p.load_sessions())
        except Exception:
            continue

    all_sessions.sort(key=lambda s: s.timestamp_end, reverse=True)

    # Attach CSM-local metadata.
    session_names.apply_custom_names(all_sessions)
    session_flags.apply_flags(all_sessions)
    return all_sessions


def search_sessions(sessions: list[SessionSummary], keyword: str) -> list[SessionSummary]:
    """按关键词搜索会话（匹配摘要、项目路径、工具名）"""

    kw = keyword.lower()
    return [
        s
        for s in sessions
        if kw in (s.custom_name or "").lower()
        or kw in s.first_display.lower()
        or kw in s.last_display.lower()
        or kw in s.project.lower()
        or kw in s.session_id.lower()
        or kw in s.tool_type.label.lower()
    ]


def group_by_project(sessions: list[SessionSummary]) -> dict[str, list[SessionSummary]]:
    """按项目分组"""

    groups: dict[str, list[SessionSummary]] = defaultdict(list)
    for s in sessions:
        groups[s.project].append(s)
    return dict(groups)


def group_by_tool(sessions: list[SessionSummary]) -> dict[ToolType, list[SessionSummary]]:
    """按工具分组"""

    groups: dict[ToolType, list[SessionSummary]] = defaultdict(list)
    for s in sessions:
        groups[s.tool_type].append(s)
    return dict(groups)


# ── 会话详情 ──


def load_session_detail(session_id: str, tool_type: ToolType, project: str = "") -> SessionDetail | None:
    """路由到对应 provider 加载详情"""

    provider = _get_provider(tool_type)
    if not provider:
        return None
    detail = provider.load_session_detail(session_id, project)
    if detail:
        session_names.apply_custom_name_to_detail(detail)
        session_flags.apply_flags_to_detail(detail)
    return detail


# ── 删除 ──


def delete_session(session_id: str, tool_type: ToolType) -> dict[str, bool]:
    """路由到对应 provider 删除会话"""

    provider = _get_provider(tool_type)
    if not provider:
        return {}
    result = provider.delete_session(session_id)

    # Best-effort: also clear CSM-local metadata for this session.
    try:
        ok, _ = session_names.set_custom_name(tool_type, session_id, "")
        result["custom_name"] = bool(ok)
    except Exception:
        result["custom_name"] = False

    try:
        ok, _ = session_flags.set_review_status(tool_type, session_id, "")
        result["review_status"] = bool(ok)
    except Exception:
        result["review_status"] = False

    return result


# ── 自定义会话名称（CSM 内部） ──


def set_session_custom_name(session_id: str, tool_type: ToolType, name: str) -> tuple[bool, str]:
    """Set or clear a tool-agnostic custom name for a session.

    By default, we also try to sync the tool-native session title so the CLI's own resume list
    reflects the change (best-effort; tools differ in what they support).
    """

    ok_local, msg_local = session_names.set_custom_name(tool_type, session_id, name)
    if not ok_local:
        # If we cannot persist CSM state, do not touch the tool's own state.
        return False, msg_local

    provider = _get_provider(tool_type)
    if not provider:
        return ok_local, f"{msg_local}; tool title: no provider"

    cleaned = " ".join((name or "").split()).strip()
    if cleaned:
        ok_tool, msg_tool = provider.set_session_title(session_id, cleaned)
    else:
        ok_tool, msg_tool = provider.clear_session_title(session_id)

    # If the provider does not support title updates, treat it as informational.
    if (not ok_tool) and msg_tool == "Not supported":
        return ok_local, f"{msg_local}; tool title: not supported"

    if ok_tool:
        extra = ""
        if msg_tool and msg_tool not in ("OK",):
            extra = f" ({msg_tool})"
        return ok_local, f"{msg_local}; tool title: OK{extra}"
    return ok_local, f"{msg_local}; tool title: FAILED ({msg_tool})"


# ── 会话标记（CSM 内部） ──


def set_session_review_status(
    session_id: str,
    tool_type: ToolType,
    status: str,
    *,
    anchor_ts_ms: int | None = None,
) -> tuple[bool, str]:
    """Set or clear review status for a session.

    status: "" | "pending" | "reviewed" | "rechecked"
    anchor_ts_ms: session timestamp_end (ms) at the moment of marking.
    """

    return session_flags.set_review_status(tool_type, session_id, status, anchor_ts_ms=anchor_ts_ms)


# ── 恢复 ──


def get_resume_command(session: SessionSummary) -> list[str]:
    """根据 session.tool_type 获取恢复命令"""

    provider = _get_provider(session.tool_type)
    if not provider:
        return []
    return provider.get_resume_command(session.session_id)


# ── 统计 ──


def load_stats() -> dict | None:
    """加载统计数据（目前仅 Claude 支持）"""

    provider = _get_provider(ToolType.CLAUDE)
    if provider:
        return provider.load_stats()
    return None
