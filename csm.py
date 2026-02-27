#!/usr/bin/env python3
"""CLI Session Manager — 多工具统一会话管理"""

import argparse
import os
import sys
from pathlib import Path

# 确保能导入 lib
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import store
from lib.logging_config import configure_logging
from lib.models import ToolType
from lib.tui import TUI
from lib.utils import ts_to_str, short_project, format_session_line
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


def _tool_slug(tool_type: ToolType) -> str:
    return {
        ToolType.CLAUDE: "claude",
        ToolType.CODEX: "codex",
        ToolType.GEMINI: "gemini",
    }.get(tool_type, tool_type.label.lower())


def _print_sessions(sessions):
    """打印会话列表（共享格式化逻辑）"""
    for s in sessions:
        meta, display = format_session_line(s, short=False)
        print(f"  {meta}  {s.session_id[:8]}")
        print(f"      {display[:60]}")
        print()


def cmd_list(args):
    """列出所有会话"""
    tool_filter = _parse_tool_filter(args)
    sessions = store.load_sessions(tool_filter)
    if not sessions:
        print("没有找到会话记录。")
        return
    _print_sessions(sessions)


def cmd_search(args):
    """搜索会话"""
    tool_filter = _parse_tool_filter(args)
    sessions = store.load_sessions(tool_filter)
    results = store.search_sessions(sessions, args.keyword)
    if not results:
        print(f'未找到匹配 "{args.keyword}" 的会话。')
        return

    print(f'找到 {len(results)} 个匹配的会话:\n')
    _print_sessions(results)


def cmd_delete(args):
    """删除会话"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    print(f"工具: {target.tool_type.label}")
    print(f"会话: {target.session_id}")
    print(f"项目: {short_project(target.project)}")
    print(f"时间: {ts_to_str(target.timestamp_end, '%Y-%m-%d %H:%M')}")

    confirm = input("\n确认删除? (y/N): ").strip().lower()
    if confirm != "y":
        print("已取消。")
        return

    result = store.delete_session(target.session_id, target.tool_type)
    deleted = [k for k, v in result.items() if v]
    print(f"已删除: {', '.join(deleted) if deleted else '无文件'}")


def cmd_resume(args):
    """恢复会话"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    cmd = store.get_resume_command(target)
    if not cmd:
        print("无法获取恢复命令。")
        return
    print(f"恢复 {target.tool_type.label} 会话: {target.session_id[:12]}...")
    os.execvp(cmd[0], cmd)


def cmd_open(args):
    """在新终端中恢复会话（当前 CSM 不退出）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    cmd = store.get_resume_command(target)
    if not cmd:
        print("无法获取恢复命令。")
        return

    ok, msg = open_in_terminal(cmd, cwd=target.project or "")
    if ok:
        print(f"已在新终端恢复 {target.tool_type.label} 会话: {target.session_id[:12]}")
    else:
        print(f"打开新终端失败: {msg}")


def cmd_handoff(args):
    """基于 handoff 快照，把会话接力到另一工具（在新终端启动）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    src = matches[0]

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
    else:
        print(f"接力失败: {msg}")


def cmd_review(args):
    """基于 handoff 快照，在另一工具开启 review-only 审查（新终端启动）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    src = matches[0]

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
    else:
        print(f"启动审查失败: {msg}")


def cmd_reviewed(args):
    """标记会话为已完成审查（CSM 本地状态）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    ok, msg = store.set_session_review_status(target.session_id, target.tool_type, "reviewed", anchor_ts_ms=int(target.timestamp_end or 0))
    if ok:
        print(f"已标记已审: [{target.tool_type.label}] {target.session_id[:12]}")
    else:
        print(f"标记失败: {msg}")


def cmd_rechecked(args):
    """标记会话为已完成复查/复验（CSM 本地状态）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    ok, msg = store.set_session_review_status(target.session_id, target.tool_type, "rechecked", anchor_ts_ms=int(target.timestamp_end or 0))
    if ok:
        print(f"已标记已复查: [{target.tool_type.label}] {target.session_id[:12]}")
    else:
        print(f"标记失败: {msg}")



def cmd_unreview(args):
    """清除会话的审查标记（CSM 本地状态）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    ok, msg = store.set_session_review_status(target.session_id, target.tool_type, "")
    if ok:
        print(f"已清除审查标记: [{target.tool_type.label}] {target.session_id[:12]}")
    else:
        print(f"清除失败: {msg}")


def cmd_name(args):
    """设置会话名称（并尽力同步到工具自身的标题/列表）"""
    sid = args.session_id
    tool_filter = _parse_tool_filter(args)

    sessions = store.load_sessions(tool_filter)
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return

    target = matches[0]
    name = " ".join(getattr(args, "name", [])).strip()
    ok, msg = store.set_session_custom_name(target.session_id, target.tool_type, name)
    if ok:
        if name:
            print(f"已设置名称: [{target.tool_type.short}] {target.session_id[:12]} -> {name}")
        else:
            print(f"已清除名称: [{target.tool_type.short}] {target.session_id[:12]}")
        if msg:
            print(f"同步状态: {msg}")
    else:
        print(f"设置名称失败: {msg}")


def cmd_stats(args):
    """显示统计信息"""
    stats = store.load_stats()
    if not stats:
        print("无统计数据。")
        return

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


def cmd_memory_sync(args):
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
    matches = [s for s in sessions if s.session_id.startswith(sid)]
    if not matches:
        print(f"未找到会话: {sid}")
        return 2
    if len(matches) > 1:
        print(f"短 ID '{sid}' 匹配到多个会话，请提供更长的 ID:")
        for m in matches:
            print(f"  [{m.tool_type.label}] {m.session_id}")
        return 2

    target = matches[0]
    print(f"同步会话 {target.session_id[:8]} ({target.tool_type.label}) 到本地 memory...")
    result = sync_session(target.session_id, _tool_slug(target.tool_type))
    if "error" in result:
        print(f"失败: {result['error']}")
        return 1
    inserted = bool(result.get("inserted"))
    print(f"同步成功（inserted={str(inserted).lower()}）。")
    return 0


def cmd_memory_search(args):
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


def cmd_memory_status(args):
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


def cmd_mcp(args):
    """启动 MCP Server（stdio 模式）"""
    from lib.mcp_server import mcp as mcp_server
    mcp_server.run(transport="stdio")


def main():
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="csm",
        description="CLI Session Manager — 多工具统一会话管理",
    )
    # 全局 --tool 参数
    parser.add_argument("--tool", choices=["claude", "codex", "gemini"],
                        help="筛选指定工具的会话")

    sub = parser.add_subparsers(dest="command")

    # 子命令
    sub.add_parser("list", aliases=["ls"], help="列出所有会话")

    p_search = sub.add_parser("search", aliases=["s"], help="搜索会话")
    p_search.add_argument("keyword", help="搜索关键词")

    p_delete = sub.add_parser("delete", aliases=["rm"], help="删除会话")
    p_delete.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")

    p_resume = sub.add_parser("resume", aliases=["r"], help="恢复会话")
    p_resume.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")

    p_open = sub.add_parser("open", aliases=["o"], help="在新终端恢复会话（当前 CSM 不退出）")
    p_open.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")

    p_handoff = sub.add_parser("handoff", aliases=["x"], help="基于 handoff 快照把会话接力到另一工具（在新终端启动）")
    p_handoff.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_handoff.add_argument("--to", choices=["claude", "codex"], help="指定接力目标工具（默认自动判断）")

    p_review = sub.add_parser("review", aliases=["v"], help="基于 handoff 快照跳转到另一工具进行审查（新终端启动）")
    p_review.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_review.add_argument("--to", choices=["claude", "codex"], help="指定审查工具（默认自动判断）")

    p_reviewed = sub.add_parser("reviewed", aliases=["rd"], help="标记会话为已完成审查（CSM 本地状态）")
    p_reviewed.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")

    p_rechecked = sub.add_parser("rechecked", aliases=["rv"], help="标记会话为已完成复查/复验（CSM 本地状态）")
    p_rechecked.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")

    p_unreview = sub.add_parser("unreview", aliases=["ru"], help="清除会话审查标记（CSM 本地状态）")
    p_unreview.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")

    p_name = sub.add_parser("name", aliases=["rename", "n"], help="设置会话名称（并尽力同步到工具自身标题）")
    p_name.add_argument("session_id", help="会话 ID（支持短 ID 前缀匹配）")
    p_name.add_argument("name", nargs=argparse.REMAINDER, help="新的名称（留空表示清除）")

    sub.add_parser("stats", help="显示使用统计")
    sub.add_parser("mcp", help="启动 MCP Server（stdio 模式，供 CLI agent 调用）")

    p_mem_sync = sub.add_parser("memory-sync", aliases=["ms"], help="同步会话数据到本地 memory 索引")
    p_mem_sync.add_argument("session_id", nargs="?", help="会话 ID（支持短 ID 前缀匹配）")
    p_mem_sync.add_argument("--all", action="store_true", help="批量同步最近会话")
    p_mem_sync.add_argument("--limit", type=int, default=20, help="批量同步数量（默认 20）")

    p_mem_search = sub.add_parser("memory-search", aliases=["mq"], help="搜索本地 memory 索引")
    p_mem_search.add_argument("query", help="搜索关键词")
    p_mem_search.add_argument("--limit", type=int, default=10, help="返回数量（默认 10）")

    sub.add_parser("memory-status", aliases=["mt"], help="查看本地 memory 存储状态")

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

    # 处理子命令
    if args.command in ("list", "ls"):
        return cmd_list(args)
    if args.command in ("search", "s"):
        return cmd_search(args)
    if args.command in ("delete", "rm"):
        return cmd_delete(args)
    if args.command in ("resume", "r"):
        return cmd_resume(args)
    if args.command in ("open", "o"):
        return cmd_open(args)
    if args.command in ("handoff", "x"):
        return cmd_handoff(args)
    if args.command in ("review", "v"):
        return cmd_review(args)
    if args.command in ("reviewed", "rd"):
        return cmd_reviewed(args)
    if args.command in ("rechecked", "rv"):
        return cmd_rechecked(args)
    if args.command in ("unreview", "ru"):
        return cmd_unreview(args)
    if args.command in ("name", "rename", "n"):
        return cmd_name(args)
    if args.command == "stats":
        return cmd_stats(args)
    if args.command == "mcp":
        return cmd_mcp(args)
    if args.command in ("memory-sync", "ms"):
        return cmd_memory_sync(args)
    if args.command in ("memory-search", "mq"):
        return cmd_memory_search(args)
    if args.command in ("memory-status", "mt"):
        return cmd_memory_status(args)

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
