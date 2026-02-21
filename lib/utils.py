"""共享工具函数"""

import unicodedata
from datetime import datetime
from pathlib import Path


def display_width(text: str) -> int:
    """计算字符串在终端中的显示宽度（CJK 字符占 2 列）"""

    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def truncate(text: str, width: int) -> str:
    """按显示宽度截断文本（CJK 安全）"""

    text = text.replace("\n", " ").replace("\r", "")
    if display_width(text) <= width:
        return text
    cur = 0
    result = []
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        cw = 2 if eaw in ("W", "F") else 1
        if cur + cw > width - 1:  # 留 1 列给省略号
            break
        result.append(ch)
        cur += cw
    return "".join(result) + "…"


def ts_to_str(ts_ms: float, fmt: str = "%m-%d %H:%M") -> str:
    """毫秒时间戳转可读字符串"""

    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime(fmt)
    except (OSError, ValueError):
        return "??-?? ??:??"


def short_project(project: str) -> str:
    """缩短项目路径，将 home 目录替换为 ~"""

    home = str(Path.home())
    if project.startswith(home):
        return "~" + project[len(home) :]
    return project


def _review_marker(review_status: str) -> str:
    rs = (review_status or "").strip().lower()
    if rs == "pending":
        return "P"
    if rs == "reviewed":
        return "R"
    if rs == "rechecked":
        return "V"
    return ""


def format_session_line(session, short: bool = False) -> tuple[str, str]:
    """格式化会话为显示行，返回 (tag_and_meta, display_text)

    short=True 时 ts 格式用短格式 mm-dd HH:MM，
    short=False 时用长格式 YYYY-mm-dd HH:MM
    """

    fmt = "%m-%d %H:%M" if short else "%Y-%m-%d %H:%M"
    time_str = ts_to_str(session.timestamp_end, fmt)
    proj = short_project(session.project)

    marker = _review_marker(getattr(session, "review_status", ""))
    tool_tag = f"[{session.tool_type.label}]"
    tag = f"{tool_tag}{marker}" if marker else tool_tag

    display = session.first_display or "(空)"
    if display.startswith("<"):
        display = session.last_display or "(命令)"
    display = display.replace("\n", " ")
    if getattr(session, "custom_name", ""):
        display = f"{session.custom_name} | {display}"

    return f"{tag} {time_str}  {proj}", display
