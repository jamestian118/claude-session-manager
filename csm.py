#!/usr/bin/env python3
"""CLI Session Manager — 多工具统一会话管理"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 确保能导入 lib
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import store
from lib.logging_config import configure_logging
from lib.models import SessionSummary, ToolType
from lib.tui import TUI
from lib.utils import _tool_slug, short_project, ts_to_str
from lib.integration import open_in_terminal, open_handoff_in_terminal, open_review_in_terminal

# --tool 参数到 ToolType 的映射
_TOOL_MAP = {
    "claude": ToolType.CLAUDE,
    "codex": ToolType.CODEX,
    "gemini": ToolType.GEMINI,
}


def _parse_tool_filter(args) -> ToolType | None:
    tool = getattr(args, "tool", None)
    if tool:
        return _TOOL_MAP.get(tool.lower())
    return None


_ANSI_RESET = "\033[0m"
_ANSI_DIM = "\033[2m"
_ANSI_CYAN = "\033[96m"
_ANSI_YELLOW = "\033[93m"
_ANSI_MAGENTA = "\033[95m"
_ANSI_BLUE = "\033[94m"


def _ansi_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _ansi(text: str, color: str) -> str:
    if not _ansi_enabled():
        return text
    return f"{color}{text}{_ANSI_RESET}"


def _review_marker(session) -> str:
    rs = (getattr(session, "review_status", "") or "").strip().lower()
    if rs == "pending":
        return "P"
    if rs == "reviewed":
        return "R"
    if rs == "rechecked":
        return "V"
    return ""


def _tool_color(tool_type: ToolType) -> str:
    if tool_type == ToolType.CLAUDE:
        return _ANSI_CYAN
    if tool_type == ToolType.CODEX:
        return _ANSI_YELLOW
    if tool_type == ToolType.GEMINI:
        return _ANSI_MAGENTA
    return _ANSI_CYAN


def _session_display_text(session) -> str:
    display = session.first_display or "(空)"
    if display.startswith("<"):
        display = session.last_display or "(命令)"
    display = display.replace("\n", " ")
    if getattr(session, "custom_name", ""):
        display = f"{session.custom_name} | {display}"
    return display


def _session_meta_text(session, *, short: bool = False, color: bool = True) -> str:
    fmt = "%m-%d %H:%M" if short else "%Y-%m-%d %H:%M"
    time_text = ts_to_str(session.timestamp_end, fmt)
    project_text = short_project(session.project)
    marker = _review_marker(session)
    tool_tag = f"[{session.tool_type.label}]"
    tag = f"{tool_tag}{marker}" if marker else tool_tag

    if color:
        tag = _ansi(tag, _tool_color(session.tool_type))
        time_text = _ansi(time_text, _ANSI_DIM)
        project_text = _ansi(project_text, _ANSI_BLUE)
    return f"{tag} {time_text}  {project_text}"


def _session_to_json(session) -> dict:
    return {
        "session_id": session.session_id,
        "tool": _tool_slug(session.tool_type),
        "tool_label": session.tool_type.label,
        "timestamp_end_ms": session.timestamp_end,
        "timestamp_end": ts_to_str(session.timestamp_end, "%Y-%m-%d %H:%M"),
        "project": session.project,
        "project_short": short_project(session.project),
        "display": _session_display_text(session),
        "custom_name": getattr(session, "custom_name", "") or "",
        "review_status": getattr(session, "review_status", "") or "",
        "message_count": int(getattr(session, "message_count", 0) or 0),
    }


def _print_sessions(sessions):
    """打印会话列表（共享格式化逻辑）"""
    for s in sessions:
        meta = _session_meta_text(s, short=False, color=True)
        display = _session_display_text(s)
        print(f"  {meta}  {s.session_id[:8]}")
        print(f"      {display[:60]}")
        print()


def _resolve_single_session(sessions: list[SessionSummary], sid: str) -> SessionSummary | None:
    sid = (sid or "").strip()
    if not sid:
        print("会话 ID 不能为空")
        return None
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return None
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return None
    return matches[0]


def cmd_list(args) -> int:
    """列出所有会话"""
    limit_value = getattr(args, "limit", None)
    if limit_value is not None:
        try:
            limit = int(limit_value)
        except (TypeError, ValueError):
            print("参数错误: --limit 必须是正整数。")
            return 2
        if limit <= 0:
            print("参数错误: --limit 必须是正整数。")
            return 2
    else:
        limit = None

    tool_filter = _parse_tool_filter(args)
    sessions = store.load_sessions(tool_filter)
    if limit is not None:
        sessions = sessions[:limit]

    if getattr(args, "json", False):
        print(json.dumps([_session_to_json(s) for s in sessions], ensure_ascii=False, indent=2))
        return 0

    if not sessions:
        print("没有找到会话记录。")
        return 0
    _print_sessions(sessions)
    return 0


def cmd_search(args) -> int:
    """搜索会话"""
    tool_filter = _parse_tool_filter(args)
    sessions = store.load_sessions(tool_filter)
    results = store.search_sessions(sessions, args.keyword)
    if not results:
        print(f'未找到匹配 "{args.keyword}" 的会话。')
        return 0

    print(f'找到 {len(results)} 个匹配的会话:\n')
    _print_sessions(results)
    return 0


def cmd_delete(args) -> int:
    """删除会话"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    print(f"工具: {_ansi(target.tool_type.label, _tool_color(target.tool_type))}")
    print(f"会话: {target.session_id}")
    print(f"项目: {_ansi(short_project(target.project), _ANSI_BLUE)}")
    print(f"时间: {_ansi(ts_to_str(target.timestamp_end, '%Y-%m-%d %H:%M'), _ANSI_DIM)}")

    confirm = input("\n确认删除? (y/N): ").strip().lower()
    if confirm != "y":
        print("已取消。")
        return 0

    result = store.delete_session(target.session_id, target.tool_type)
    deleted = [k for k, v in result.items() if v]
    if deleted:
        print(f"已删除: {', '.join(deleted)}")
        return 0
    print("删除失败: 无文件被删除。")
    return 1


def cmd_resume(args) -> int:
    """恢复会话"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    cmd = store.get_resume_command(target)
    if not cmd:
        print("无法获取恢复命令。")
        return 1
    print(f"恢复 {target.tool_type.label} 会话: {target.session_id[:12]}...")
    try:
        os.execvp(cmd[0], cmd)
    except OSError as e:
        print(f"恢复失败: {e}")
        return 1
    return 0


def cmd_open(args) -> int:
    """在新终端中恢复会话（当前 CSM 不退出）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    cmd = store.get_resume_command(target)
    if not cmd:
        print("无法获取恢复命令。")
        return 1

    ok, msg = open_in_terminal(cmd, cwd=target.project or "")
    if ok:
        print(f"已在新终端恢复 {target.tool_type.label} 会话: {target.session_id[:12]}")
        return 0
    else:
        print(f"打开新终端失败: {msg}")
        return 1


def cmd_handoff(args) -> int:
    """基于 handoff 快照，把会话接力到另一工具（在新终端启动）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    src = _resolve_single_session(sessions, sid)
    if not src:
        return 2

    # Default: Claude -> Codex, Codex -> Claude.
    if getattr(args, "to", None):
        target_tool = _TOOL_MAP.get(args.to.lower())
    else:
        if src.tool_type == ToolType.CLAUDE:
            target_tool = ToolType.CODEX
        elif src.tool_type == ToolType.CODEX:
            target_tool = ToolType.CLAUDE
        else:
            target_tool = ToolType.CODEX

    ok, msg = open_handoff_in_terminal(src, target_tool)
    if ok:
        print(f"已在新终端启动接力: {src.tool_type.label} -> {target_tool.label} ({src.session_id[:12]})")
        return 0
    else:
        print(f"接力失败: {msg}")
        return 1


def cmd_review(args) -> int:
    """基于 handoff 快照，在另一工具开启 review-only 审查（新终端启动）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    src = _resolve_single_session(sessions, sid)
    if not src:
        return 2

    # Default: Claude -> Codex, Codex -> Claude.
    if getattr(args, "to", None):
        target_tool = _TOOL_MAP.get(args.to.lower())
    else:
        if src.tool_type == ToolType.CLAUDE:
            target_tool = ToolType.CODEX
        elif src.tool_type == ToolType.CODEX:
            target_tool = ToolType.CLAUDE
        else:
            target_tool = ToolType.CODEX

    ok, msg = open_review_in_terminal(src, target_tool)
    if ok:
        # Mark pending (best-effort) so you can track review workflow in CSM.
        ok_flag, msg_flag = store.set_session_review_status(src.session_id, src.tool_type, "pending", anchor_ts_ms=int(src.timestamp_end or 0))
        if not ok_flag:
            print(f"(警告) 无法标记 review 状态: {msg_flag}")

        print(f"已在新终端启动审查: [{src.tool_type.label}] -> [{target_tool.label}] ({src.session_id[:12]})")
        return 0
    else:
        print(f"启动审查失败: {msg}")
        return 1


def cmd_reviewed(args) -> int:
    """标记会话为已完成审查（CSM 本地状态）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    ok, msg = store.set_session_review_status(target.session_id, target.tool_type, "reviewed", anchor_ts_ms=int(target.timestamp_end or 0))
    if ok:
        print(f"已标记已审: [{target.tool_type.label}] {target.session_id[:12]}")
        return 0
    else:
        print(f"标记失败: {msg}")
        return 1


def cmd_rechecked(args) -> int:
    """标记会话为已完成复查/复验（CSM 本地状态）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    ok, msg = store.set_session_review_status(target.session_id, target.tool_type, "rechecked", anchor_ts_ms=int(target.timestamp_end or 0))
    if ok:
        print(f"已标记已复查: [{target.tool_type.label}] {target.session_id[:12]}")
        return 0
    else:
        print(f"标记失败: {msg}")
        return 1



def cmd_unreview(args) -> int:
    """清除会话的审查标记（CSM 本地状态）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    ok, msg = store.set_session_review_status(target.session_id, target.tool_type, "")
    if ok:
        print(f"已清除审查标记: [{target.tool_type.label}] {target.session_id[:12]}")
        return 0
    else:
        print(f"清除失败: {msg}")
        return 1


def cmd_name(args) -> int:
    """设置会话名称（并尽力同步到工具自身的标题/列表）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    name = " ".join(getattr(args, "name", [])).strip()
    ok, msg = store.set_session_custom_name(target.session_id, target.tool_type, name)
    if ok:
        if name:
            print(f"已设置名称: [{target.tool_type.short}] {target.session_id[:12]} -> {name}")
        else:
            print(f"已清除名称: [{target.tool_type.short}] {target.session_id[:12]}")
        if msg:
            print(f"同步状态: {msg}")
        return 0
    else:
        print(f"设置名称失败: {msg}")
        return 1


def cmd_stats(args) -> int:
    """显示统计信息"""
    stats = store.load_stats()
    if not stats:
        print("无统计数据。")
        return 0

    daily = stats.get("dailyActivity", [])
    if daily:
        print("最近活动:")
        print(f"  {'日期':<12} {'消息':>8} {'会话':>8} {'工具调用':>8}")
        print("  " + "─" * 40)
        for d in daily[-14:]:
            date = d.get("date", "?")
            msgs = d.get("messageCount", 0)
            sess = d.get("sessionCount", 0)
            tools = d.get("toolCallCount", 0)
            print(f"  {date:<12} {msgs:>8} {sess:>8} {tools:>8}")

        total_msgs = sum(d.get("messageCount", 0) for d in daily)
        total_sess = sum(d.get("sessionCount", 0) for d in daily)
        print(f"\n  总计: {total_msgs:,} 消息, {total_sess:,} 会话")
    return 0


def cmd_memory_sync(args) -> int:
    """同步会话数据到本地 memory 索引"""
    from lib.local_memory import sync_session, sync_all_recent

    if getattr(args, "all", False):
        limit = getattr(args, "limit", 20)
        print(f"批量同步最近 {limit} 个会话到本地 memory...")
        results = sync_all_recent(limit)
        ok = sum(1 for r in results if "error" not in r.get("result", {}))
        failed = len(results) - ok
        print(f"完成: {ok}/{len(results)} 成功")
        for r in results:
            status = "OK" if "error" not in r.get("result", {}) else r["result"]["error"]
            print(f"  [{r['tool']}] {r['session_id'][:8]} — {status}")
        return 1 if failed else 0

    sid = getattr(args, "session_id", None)
    if not sid:
        print("请指定 session_id 或使用 --all")
        return 2

    tool_filter = _parse_tool_filter(args)
    sessions = store.load_sessions(tool_filter)
    target = _resolve_single_session(sessions, sid)
    if not target:
        return 2
    print(f"同步会话 {target.session_id[:8]} ({target.tool_type.label}) 到本地 memory...")
    result = sync_session(target.session_id, _tool_slug(target.tool_type))
    if "error" in result:
        print(f"失败: {result['error']}")
        return 1
    inserted = bool(result.get("inserted"))
    print(f"同步成功（inserted={str(inserted).lower()}）。")
    return 0


def cmd_memory_search(args) -> int:
    """搜索本地 memory 索引"""
    from lib.local_memory import search_memory

    limit = max(1, int(getattr(args, "limit", 10) or 10))
    rows = search_memory(args.query, limit=limit)
    if not rows:
        print(f'未找到匹配 "{args.query}" 的 memory 记录。')
        return 0

    print(f"找到 {len(rows)} 条 memory 记录:\n")
    for i, r in enumerate(rows, start=1):
        title = r.get("title", "")
        summary = str(r.get("summary", "")).replace("\n", " ")
        if len(summary) > 120:
            summary = summary[:119] + "…"
        print(f"{i:>2}. [{r.get('tool', '?')}] {r.get('session_id', '')[:8]}  {title}")
        print(f"    project: {r.get('project', '')}")
        print(f"    updated: {r.get('updated_at', '')}")
        print(f"    summary: {summary}")
        print()
    return 0


def cmd_memory_status(args) -> int:
    """查看本地 memory 存储状态"""
    from lib.local_memory import get_status

    status = get_status()
    print(f"enabled: {status.get('enabled', False)}")
    print(f"db_path: {status.get('db_path', '')}")
    if status.get("error"):
        print(f"error: {status['error']}")
        return 1
    print(f"entries: {status.get('entries', 0)}")
    print(f"sessions: {status.get('sessions', 0)}")
    print(f"latest_updated_at: {status.get('latest_updated_at', '')}")
    print(f"db_size_bytes: {status.get('db_size_bytes', 0)}")
    return 0


def cmd_mcp(args) -> int:
    """启动 MCP Server（stdio 模式）"""
    try:
        from lib.mcp_server import mcp as mcp_server
        mcp_server.run(transport="stdio")
        return 0
    except Exception as e:
        print(f"启动 MCP Server 失败: {e}")
        return 1


def main():
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="csm",
        description="CLI Session Manager — 多工具统一会话管理（无参数 = 启动 TUI）",
    )
    # 全局 --tool 参数
    parser.add_argument("--tool", choices=["claude", "codex", "gemini"],
                        help="筛选指定工具的会话")

    sub = parser.add_subparsers(dest="command")

    # 子命令
    p_list = sub.add_parser("list", aliases=["ls"], help="列出所有会话")
    p_list.add_argument("--limit", type=int, help="最多显示前 N 条（按时间倒序）")
    p_list.add_argument("--json", action="store_true", help="以 JSON 输出会话列表")
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search", aliases=["s"], help="搜索会话")
    p_search.add_argument("keyword", help="搜索关键词")
    p_search.set_defaults(func=cmd_search)

    p_delete = sub.add_parser("delete", aliases=["rm"], help="删除会话")
    p_delete.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_delete.set_defaults(func=cmd_delete)

    p_resume = sub.add_parser("resume", aliases=["r"], help="恢复会话")
    p_resume.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_resume.set_defaults(func=cmd_resume)

    p_open = sub.add_parser("open", aliases=["o"], help="在新终端恢复会话（当前 CSM 不退出）")
    p_open.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_open.set_defaults(func=cmd_open)

    p_handoff = sub.add_parser("handoff", aliases=["x"], help="基于 handoff 快照把会话接力到另一工具（在新终端启动）")
    p_handoff.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_handoff.add_argument("--to", choices=["claude", "codex"], help="指定接力目标工具（默认自动判断）")
    p_handoff.set_defaults(func=cmd_handoff)

    p_review = sub.add_parser("review", aliases=["v"], help="基于 handoff 快照跳转到另一工具进行审查（新终端启动）")
    p_review.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_review.add_argument("--to", choices=["claude", "codex"], help="指定审查工具（默认自动判断）")
    p_review.set_defaults(func=cmd_review)

    p_reviewed = sub.add_parser("reviewed", aliases=["rd"], help="标记会话为已完成审查（CSM 本地状态）")
    p_reviewed.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_reviewed.set_defaults(func=cmd_reviewed)

    p_rechecked = sub.add_parser("rechecked", aliases=["rv"], help="标记会话为已完成复查/复验（CSM 本地状态）")
    p_rechecked.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_rechecked.set_defaults(func=cmd_rechecked)

    p_unreview = sub.add_parser("unreview", aliases=["ru"], help="清除会话审查标记（CSM 本地状态）")
    p_unreview.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_unreview.set_defaults(func=cmd_unreview)

    p_name = sub.add_parser("name", aliases=["rename", "n"], help="设置会话名称（并尽力同步到工具自身标题）")
    p_name.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_name.add_argument("name", nargs=argparse.REMAINDER, help="新的名称（留空表示清除）")
    p_name.set_defaults(func=cmd_name)

    p_stats = sub.add_parser("stats", help="显示使用统计")
    p_stats.set_defaults(func=cmd_stats)
    p_mcp = sub.add_parser("mcp", help="启动 MCP Server（stdio 模式，供 CLI agent 调用）")
    p_mcp.set_defaults(func=cmd_mcp)

    p_mem_sync = sub.add_parser("memory-sync", aliases=["ms"], help="同步会话数据到本地 memory 索引")
    p_mem_sync.add_argument("session_id", nargs="?", help="会话 ID（支持短 ID 前缀匹配）")
    p_mem_sync.add_argument("--all", action="store_true", help="批量同步最近会话")
    p_mem_sync.add_argument("--limit", type=int, default=20, help="批量同步数量（默认 20）")
    p_mem_sync.set_defaults(func=cmd_memory_sync)

    p_mem_search = sub.add_parser("memory-search", aliases=["mq"], help="搜索本地 memory 索引")
    p_mem_search.add_argument("query", help="搜索关键词")
    p_mem_search.add_argument("--limit", type=int, default=10, help="返回数量（默认 10）")
    p_mem_search.set_defaults(func=cmd_memory_search)

    p_mem_status = sub.add_parser("memory-status", aliases=["mt"], help="查看本地 memory 存储状态")
    p_mem_status.set_defaults(func=cmd_memory_status)

    # 兼容 --list 等旧参数
    parser.add_argument("--list", action="store_true", help="列出所有会话")
    parser.add_argument("--search", metavar="KEYWORD", help="搜索会话")
    parser.add_argument("--delete", metavar="ID", help="删除会话")
    parser.add_argument("--resume", metavar="ID", help="恢复会话")
    parser.add_argument("--stats", action="store_true", help="显示统计")

    args = parser.parse_args()

    # 处理 --flag 风格参数
    if args.list:
        return cmd_list(args)
    if args.search:
        args.keyword = args.search
        return cmd_search(args)
    if args.delete:
        args.session_id = args.delete
        return cmd_delete(args)
    if args.resume:
        args.session_id = args.resume
        return cmd_resume(args)
    if args.stats:
        return cmd_stats(args)

    # 处理子命令（argparse set_defaults 路由）
    if hasattr(args, "func"):
        return args.func(args)

    # 无参数 → 启动 TUI
    tool_filter = _parse_tool_filter(args)
    tui = TUI(tool_filter=tool_filter)
    resume_session = tui.run()
    if resume_session:
        cmd = store.get_resume_command(resume_session)
        if cmd:
            print(f"恢复 {resume_session.tool_type.label} 会话: {resume_session.session_id[:12]}...")
            os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    raise SystemExit(main() or 0)
