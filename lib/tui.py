"""curses 交互式 TUI 界面"""

import curses
import locale
import logging
import os
import subprocess
import sys
import termios
from .models import ToolType, SessionSummary, SessionDetail
from . import store
from .integration import open_in_terminal, open_handoff_in_terminal, open_review_in_terminal
try:
    from .integration import open_mcp_handoff_in_terminal
except ImportError:
    open_mcp_handoff_in_terminal = None
from .utils import display_width, truncate, ts_to_str, short_project

logger = logging.getLogger(__name__)


# 工具筛选循环顺序
_TOOL_CYCLE = [None, ToolType.CLAUDE, ToolType.CODEX, ToolType.GEMINI]


class TUI:
    def __init__(self, tool_filter: ToolType | None = None):
        self.sessions: list[SessionSummary] = []
        self.filtered: list[SessionSummary] = []
        self.cursor = 0
        self.offset = 0  # 滚动偏移
        self.search_query = ""
        self.mode = "list"  # list / detail / search / group / stats / help
        self.detail: SessionDetail | None = None
        self.detail_scroll = 0
        self._detail_lines: list[tuple[str, int]] = []  # 详情缓存
        self.group_data: dict[str, list[SessionSummary]] = {}
        self.group_keys: list[str] = []
        self.group_cursor = 0
        self.group_offset = 0
        self.stats: dict | None = None
        self.stats_scroll = 0
        self.resume_session: SessionSummary | None = None  # 退出后恢复的会话
        self.tool_filter: ToolType | None = tool_filter

    def run(self):
        """启动 TUI，返回需要恢复的 SessionSummary 或 None"""
        locale.setlocale(locale.LC_ALL, "")
        self.sessions = store.load_sessions(self.tool_filter)
        self.filtered = self.sessions[:]
        curses.wrapper(self._main)
        return self.resume_session

    def _reload_sessions(self):
        """重新加载会话列表"""
        self.sessions = store.load_sessions(self.tool_filter)
        if self.search_query:
            self.filtered = store.search_sessions(self.sessions, self.search_query)
        else:
            self.filtered = self.sessions[:]

    def _main(self, stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        # 初始化颜色对
        curses.init_pair(1, curses.COLOR_CYAN, -1)     # 标题 / Claude
        curses.init_pair(2, curses.COLOR_GREEN, -1)     # 高亮选中
        curses.init_pair(3, curses.COLOR_YELLOW, -1)    # 时间 / Codex
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)   # 项目路径 / Gemini
        curses.init_pair(5, curses.COLOR_RED, -1)       # 警告/删除
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)  # 状态栏
        curses.init_pair(7, curses.COLOR_BLUE, -1)      # assistant 消息

        self.stdscr = stdscr
        stdscr.timeout(100)

        while True:
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            if self.mode == "list":
                self._draw_list(stdscr, h, w)
            elif self.mode == "detail":
                self._draw_detail(stdscr, h, w)
            elif self.mode == "group":
                self._draw_group(stdscr, h, w)
            elif self.mode == "stats":
                self._draw_stats(stdscr, h, w)
            elif self.mode == "help":
                self._draw_help(stdscr, h, w)

            stdscr.refresh()
            key = stdscr.getch()
            if key == -1:
                continue

            if self.mode == "list":
                if not self._handle_list_key(key, h):
                    break
            elif self.mode == "detail":
                self._handle_detail_key(key, h)
            elif self.mode == "group":
                self._handle_group_key(key, h)
            elif self.mode == "stats":
                self._handle_stats_key(key, h)
            elif self.mode == "help":
                if key in (ord("q"), 27):
                    self.mode = "list"

    # ── 列表视图 ──

    def _filter_label(self) -> str:
        """当前筛选标签"""
        if self.tool_filter:
            return self.tool_filter.label
        return "全部"

    def _draw_list(self, scr, h, w):
        # 标题栏
        title = f" CSM [{self._filter_label()}] — {len(self.filtered)} 个会话"
        if self.search_query:
            title += f'  [搜索: "{self.search_query}"]'
        scr.addnstr(0, 0, title, w - 1, curses.color_pair(1) | curses.A_BOLD)

        # 列表区域
        list_h = h - 3  # 留出标题和底部状态栏
        if list_h < 1:
            return

        # 调整滚动
        if self.cursor < self.offset:
            self.offset = self.cursor
        if self.cursor >= self.offset + list_h:
            self.offset = self.cursor - list_h + 1

        for i in range(list_h):
            idx = self.offset + i
            if idx >= len(self.filtered):
                break
            s = self.filtered[idx]
            y = i + 1
            is_sel = idx == self.cursor

            time_str = ts_to_str(s.timestamp_end)
            proj = short_project(s.project)
            display = s.first_display or "(空)"
            # 过滤掉 XML 标签内容
            if display.startswith("<"):
                display = s.last_display or "(命令)"
            if s.custom_name:
                display = f"{s.custom_name} | {display}"

            # 工具标识前缀
            tool_tag = f"[{s.tool_type.label}]"

            # Review status marker (CSM-local):
            # - pending  -> P (red)
            # - reviewed -> R (yellow)
            # - rechecked -> V (green)
            review_tag = ""
            review_attr = 0
            rs = (s.review_status or "").strip().lower()
            if rs == "pending":
                review_tag = "P"
                review_attr = curses.color_pair(5) | curses.A_BOLD
            elif rs == "reviewed":
                review_tag = "R"
                review_attr = curses.color_pair(3) | curses.A_BOLD
            elif rs == "rechecked":
                review_tag = "V"
                review_attr = curses.color_pair(2) | curses.A_BOLD

            # 格式: [工具][审查标记] [时间] 项目 | 消息摘要
            prefix = f" {tool_tag}{review_tag} {time_str}  {proj}"
            prefix_dw = display_width(prefix)
            remaining = w - prefix_dw - 4
            msg = truncate(display, max(remaining, 10))
            line = f"{prefix}  {msg}"

            attr = curses.A_REVERSE if is_sel else 0
            try:
                scr.addnstr(y, 0, line.ljust(w - 1), w - 1, attr)
                if not is_sel:
                    # 工具标识颜色 — 纯 ASCII，display_width == len
                    tag_dw = len(tool_tag)
                    scr.chgat(y, 1, tag_dw, curses.color_pair(s.tool_type.color_index))
                    if review_tag:
                        scr.chgat(y, 1 + tag_dw, 1, review_attr)
                    # 时间颜色
                    time_start = 1 + tag_dw + len(review_tag) + 1
                    scr.chgat(y, time_start, len(time_str), curses.color_pair(3))
                    # 项目颜色 — 路径可能包含 CJK，使用 byte 偏移
                    # chgat 按字节列工作，这里用 encode 计算 prefix 的实际列偏移
                    proj_start = time_start + len(time_str) + 2
                    proj_dw = display_width(proj)
                    scr.chgat(y, proj_start, proj_dw, curses.color_pair(4))
            except curses.error:
                pass

        # 底部状态栏
        status = " j/k:移动  Space/b:翻页  Enter:详情  /:搜索  Tab:筛选  d:删除  r:恢复  o:新终端  x:接力(选CLI)  v:流程  R:审  V:复  U:清  n:命名  q:退出"
        try:
            scr.addnstr(h - 1, 0, status.ljust(w), w - 1, curses.color_pair(6))
        except curses.error:
            pass

    def _handle_list_key(self, key, h) -> bool:
        """处理列表模式按键，返回 False 表示退出"""
        list_h = h - 3
        n = len(self.filtered)

        if key in (ord("j"), curses.KEY_DOWN):
            if self.cursor < n - 1:
                self.cursor += 1
        elif key in (ord("k"), curses.KEY_UP):
            if self.cursor > 0:
                self.cursor -= 1
        elif key in (ord("g"),):  # 跳到顶部
            self.cursor = 0
            self.offset = 0
        elif key in (ord("G"),):  # 跳到底部
            self.cursor = max(0, n - 1)
        elif key == ord(" "):  # 向下翻页
            self.cursor = min(self.cursor + list_h, max(0, n - 1))
        elif key == ord("b"):  # 向上翻页
            self.cursor = max(0, self.cursor - list_h)
        elif key == 4:  # Ctrl+D 半页下
            self.cursor = min(self.cursor + list_h // 2, max(0, n - 1))
        elif key == 21:  # Ctrl+U 半页上
            self.cursor = max(0, self.cursor - list_h // 2)
        elif key == ord("\n") or key == curses.KEY_ENTER:
            self._enter_detail()
        elif key == ord("/"):
            self._do_search()
        elif key == ord("\t"):  # Tab 键切换工具筛选
            self._cycle_tool_filter()
        elif key == ord("d"):
            self._do_delete()
        elif key == ord("r"):
            self._do_resume()
            if self.resume_session:
                return False
        elif key == ord("o"):
            self._do_open_in_terminal()
        elif key == ord("x"):
            self._do_handoff()
        elif key == ord("v"):
            self._do_review()
        elif key == ord("R"):
            self._do_mark_review_done()
        elif key == ord("V"):
            self._do_mark_recheck_done()
        elif key == ord("U"):
            self._do_clear_review_status()
        elif key == ord("n"):
            self._do_name()
        elif key == ord("p"):
            self._enter_group()
        elif key == ord("s"):
            self._enter_stats()
        elif key == ord("?"):
            self.mode = "help"
        elif key in (ord("q"), 27):
            return False
        return True

    def _cycle_tool_filter(self):
        """循环切换工具筛选"""
        try:
            idx = _TOOL_CYCLE.index(self.tool_filter)
        except ValueError:
            idx = 0
        self.tool_filter = _TOOL_CYCLE[(idx + 1) % len(_TOOL_CYCLE)]
        self._reload_sessions()
        self.cursor = 0
        self.offset = 0

    def _do_search(self):
        """搜索输入（支持中文）"""
        curses.curs_set(1)
        h, w = self.stdscr.getmaxyx()
        prompt = "搜索: "
        prompt_dw = display_width(prompt)
        try:
            self.stdscr.addnstr(h - 1, 0, prompt.ljust(w), w - 1, curses.color_pair(6))
        except curses.error:
            pass
        self.stdscr.refresh()

        query = ""
        while True:
            display_line = prompt + query
            try:
                self.stdscr.addnstr(h - 1, 0, display_line.ljust(w), w - 1, curses.color_pair(6))
                cursor_x = min(prompt_dw + display_width(query), w - 1)
                self.stdscr.move(h - 1, cursor_x)
            except curses.error:
                pass
            self.stdscr.refresh()

            self.stdscr.timeout(-1)
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                self.stdscr.timeout(100)
                continue
            self.stdscr.timeout(100)

            if isinstance(ch, str):
                if ch == "\n":
                    break
                elif ch == "\x1b":  # ESC
                    query = ""
                    break
                elif ch in ("\x7f", "\b"):  # Backspace
                    query = query[:-1]
                else:
                    query += ch
            else:
                # int 类型的特殊键
                if ch in (curses.KEY_ENTER, 10, 13):
                    break
                elif ch == 27:
                    query = ""
                    break
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    query = query[:-1]

        curses.curs_set(0)
        self.search_query = query
        if query:
            self.filtered = store.search_sessions(self.sessions, query)
        else:
            self.filtered = self.sessions[:]
        self.cursor = 0
        self.offset = 0

    def _do_name(self):
        """修改当前会话名称（CSM 内部显示用）"""
        if not self.filtered:
            return

        s = self.filtered[self.cursor]
        default = s.custom_name or ""

        mode = os.environ.get("CSM_TUI_NAME_INPUT", "").strip().lower()
        # Default to terminal prompt: supports arrow-key editing + IME better than raw curses.
        if mode not in ("terminal", "curses", "dialog"):
            mode = "terminal"

        query: str | None = None
        if mode == "dialog":
            query = self._prompt_name_dialog(s, default=default)
            if query is None:
                return
        elif mode == "curses":
            query = self._prompt_name_curses(default=default)
            if query is None:
                self._flash_status("已取消命名", color=4, ms=900)
                return
        else:
            query = self._prompt_name_terminal(s, default=default)
            if query is None:
                self._flash_status("已取消命名", color=4, ms=900)
                return

        new_name = " ".join((query or "").split()).strip()

        ok, out = store.set_session_custom_name(s.session_id, s.tool_type, new_name)
        if ok:
            prev_sid = s.session_id
            prev_tool = s.tool_type
            self._reload_sessions()
            # Keep cursor on the same session if possible.
            for i, ss in enumerate(self.filtered):
                if ss.session_id == prev_sid and ss.tool_type == prev_tool:
                    self.cursor = i
                    break
            if out and "tool title: FAILED" in out:
                if new_name:
                    self._flash_status("已命名，但工具标题同步失败", color=5, ms=2400)
                else:
                    self._flash_status("已清除名称，但工具标题同步失败", color=5, ms=2400)
            else:
                if new_name:
                    self._flash_status(f"已命名: {new_name}")
                else:
                    self._flash_status("已清除名称")
        else:
            self._flash_status(f"命名失败: {out[:60] if out else 'unknown'}", color=5, ms=2200)

    def _prompt_name_dialog(self, session: SessionSummary, default: str = "") -> str | None:
        """Prompt for a name using a native macOS dialog (best IME support).

        Controlled by env var: CSM_TUI_NAME_INPUT=dialog
        Returns None if cancelled.
        """
        if sys.platform != "darwin":
            self._flash_status("dialog 输入仅支持 macOS", color=5, ms=1800)
            return None

        prompt = f"命名 [{session.tool_type.short}] {session.session_id[:12]} (空=清除)"
        # Avoid escaping issues by passing as argv to AppleScript.
        applescript = r"""
on run argv
  set p to item 1 of argv
  set d to ""
  if (count of argv) >= 2 then
    set d to item 2 of argv
  end if
  try
    set resp to display dialog p default answer d buttons {"Cancel", "OK"} default button "OK"
    return text returned of resp
  on error number -128
    return "__CSM_CANCEL__9f7a0c2e__"
  end try
end run
"""
        try:
            p = subprocess.run(
                ["osascript", "-e", applescript, prompt, default],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            self._flash_status(f"dialog 失败: {str(e)[:40]}", color=5, ms=2200)
            return None

        out = (p.stdout or "").strip()
        if out == "__CSM_CANCEL__9f7a0c2e__":
            return None
        if p.returncode != 0:
            # Treat as cancel/failure (do not fall back implicitly; avoid surprising the user).
            return None
        return out

    def _prompt_name_terminal(self, session: SessionSummary, default: str = "") -> str | None:
        """Prompt for a name using normal terminal line editing (readline).

        This avoids many curses IME issues on macOS and supports left/right cursor movement.
        Returns None if cancelled.
        """
        try:
            import readline  # noqa: F401
        except Exception:
            readline = None  # type: ignore

        # Suspend curses UI temporarily.
        try:
            curses.def_prog_mode()
        except Exception as e:
            logger.debug("failed to save curses program mode before terminal prompt: error=%s", e)

        # Restore a sane "shell" terminal mode before leaving curses. This is critical for
        # `input()` / readline to actually echo what the user types.
        try:
            curses.nocbreak()
        except Exception as e:
            logger.debug("failed to disable cbreak for terminal prompt: error=%s", e)
        try:
            curses.noraw()
        except Exception as e:
            logger.debug("failed to disable raw mode for terminal prompt: error=%s", e)
        try:
            curses.echo()
        except Exception as e:
            logger.debug("failed to enable echo for terminal prompt: error=%s", e)
        try:
            self.stdscr.keypad(False)
        except Exception as e:
            logger.debug("failed to disable keypad for terminal prompt: error=%s", e)

        try:
            curses.endwin()
        except Exception as e:
            logger.debug("failed to leave curses mode for terminal prompt: error=%s", e)

        fd = None
        old_tio = None
        try:
            fd = sys.stdin.fileno()
            if os.isatty(fd):
                old_tio = termios.tcgetattr(fd)
                new_tio = termios.tcgetattr(fd)
                # Force a sane "cooked" mode so readline + IME composition can echo normally.
                new_tio[3] |= (termios.ECHO | termios.ICANON | termios.ISIG)
                termios.tcsetattr(fd, termios.TCSADRAIN, new_tio)
        except Exception:
            fd = None
            old_tio = None

        # Give the user enough context to avoid renaming the wrong session.
        proj = short_project(session.project or "")
        header = f"[{session.tool_type.short}] {session.session_id[:12]}"
        if proj and proj != "~":
            header += f"  {proj}"
        current = (session.custom_name or "").strip()
        preview = (session.first_display or session.last_display or "").strip()
        if preview.startswith("<"):
            preview = (session.last_display or preview).strip()
        preview = truncate(preview, 120) if preview else ""

        print()
        print("命名会话:", header)
        print("当前名称:", current if current else "(未设置)")
        if preview:
            print("摘要:", preview)
        sys.stdout.flush()

        prompt = f"新名称 (空=清除, Ctrl+C=取消; 当前={current if current else '未设置'}): "
        try:
            if default and readline is not None:
                import readline as _rl

                def _prefill():
                    _rl.insert_text(default)
                    _rl.redisplay()

                _rl.set_startup_hook(_prefill)
            else:
                try:
                    import readline as _rl
                    _rl.set_startup_hook(None)
                except Exception as e:
                    logger.debug("failed to clear readline startup hook before prompt: error=%s", e)

            try:
                return input(prompt)
            finally:
                if readline is not None:
                    try:
                        import readline as _rl
                        _rl.set_startup_hook(None)
                    except Exception as e:
                        logger.debug("failed to clear readline startup hook after prompt: error=%s", e)
        except (KeyboardInterrupt, EOFError):
            return None
        finally:
            if old_tio is not None and fd is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_tio)
                except Exception as e:
                    logger.debug("failed to restore terminal attributes after prompt: error=%s", e)
            # Restore curses program mode.
            try:
                curses.reset_prog_mode()
            except Exception as e:
                logger.debug("failed to restore curses program mode: error=%s", e)
            try:
                curses.noecho()
                curses.cbreak()
            except Exception as e:
                logger.debug("failed to restore curses input mode: error=%s", e)
            try:
                self.stdscr.keypad(True)
            except Exception as e:
                logger.debug("failed to re-enable keypad after prompt: error=%s", e)
            try:
                curses.curs_set(0)
            except Exception as e:
                logger.debug("failed to hide cursor after prompt: error=%s", e)
            try:
                self.stdscr.erase()
                self.stdscr.refresh()
            except Exception as e:
                logger.debug("failed to refresh screen after prompt: error=%s", e)

    def _prompt_name_curses(self, default: str = "") -> str | None:
        """Inline curses editor (fallback / power-user mode).

        Controlled by env var: CSM_TUI_NAME_INPUT=curses
        Returns None if cancelled.
        """
        curses.curs_set(1)
        h, w = self.stdscr.getmaxyx()
        prompt = "命名: "
        prompt_dw = display_width(prompt)
        avail_w = max(5, (w - 1) - prompt_dw)

        query = default
        cursor = len(query)
        view_start = 0

        def _fit_slice(text: str, start: int, max_w: int) -> tuple[str, int]:
            cur_w = 0
            out = []
            i = start
            while i < len(text):
                ch = text[i]
                cw = 2 if display_width(ch) == 2 else 1
                if cur_w + cw > max_w:
                    break
                out.append(ch)
                cur_w += cw
                i += 1
            return "".join(out), i

        while True:
            # Keep cursor visible by adjusting view_start.
            if cursor < view_start:
                view_start = cursor
            while view_start < cursor and display_width(query[view_start:cursor]) > avail_w:
                view_start += 1

            view_text, view_end = _fit_slice(query, view_start, avail_w)
            if cursor > view_end:
                view_start = cursor
                continue

            try:
                self.stdscr.addnstr(
                    h - 1,
                    0,
                    (prompt + view_text).ljust(w),
                    w - 1,
                    curses.color_pair(6),
                )
                cursor_x = min(prompt_dw + display_width(query[view_start:cursor]), w - 1)
                self.stdscr.move(h - 1, cursor_x)
            except curses.error:
                pass
            self.stdscr.refresh()

            self.stdscr.timeout(-1)
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                self.stdscr.timeout(100)
                continue
            self.stdscr.timeout(100)

            if isinstance(ch, str):
                if ch == "\n":
                    break
                if ch == "\x1b":  # ESC: cancel
                    curses.curs_set(0)
                    return None
                if ch in ("\x7f", "\b"):  # Backspace
                    if cursor > 0:
                        query = query[:cursor - 1] + query[cursor:]
                        cursor -= 1
                else:
                    query = query[:cursor] + ch + query[cursor:]
                    cursor += len(ch)
            else:
                if ch in (curses.KEY_ENTER, 10, 13):
                    break
                if ch == 27:
                    curses.curs_set(0)
                    return None
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    if cursor > 0:
                        query = query[:cursor - 1] + query[cursor:]
                        cursor -= 1
                elif ch == curses.KEY_LEFT:
                    if cursor > 0:
                        cursor -= 1
                elif ch == curses.KEY_RIGHT:
                    if cursor < len(query):
                        cursor += 1
                elif ch in (curses.KEY_HOME,):
                    cursor = 0
                elif ch in (curses.KEY_END,):
                    cursor = len(query)
                elif ch == curses.KEY_DC:  # Delete
                    if cursor < len(query):
                        query = query[:cursor] + query[cursor + 1:]

        curses.curs_set(0)
        return query

    def _do_delete(self):
        """删除当前选中的会话"""
        if not self.filtered:
            return
        s = self.filtered[self.cursor]
        h, w = self.stdscr.getmaxyx()

        # 确认提示
        tag = f"[{s.tool_type.short}] "
        msg = f" 确认删除 {tag}{s.session_id[:8]}...? (y/N) "
        try:
            self.stdscr.addnstr(h - 1, 0, msg.ljust(w), w - 1, curses.color_pair(5) | curses.A_BOLD)
        except curses.error:
            pass
        self.stdscr.refresh()

        self.stdscr.timeout(-1)
        ch = self.stdscr.getch()
        self.stdscr.timeout(100)

        if ch in (ord("y"), ord("Y")):
            result = store.delete_session(s.session_id, s.tool_type)
            self._reload_sessions()
            if self.cursor >= len(self.filtered):
                self.cursor = max(0, len(self.filtered) - 1)

            # 显示结果
            deleted = [k for k, v in result.items() if v]
            msg = f" 已删除: {', '.join(deleted) if deleted else '无文件'} "
            try:
                self.stdscr.addnstr(h - 1, 0, msg.ljust(w), w - 1, curses.color_pair(2))
            except curses.error:
                pass
            self.stdscr.refresh()
            curses.napms(1200)

    def _do_resume(self):
        """标记恢复会话"""
        if not self.filtered:
            return
        s = self.filtered[self.cursor]
        self.resume_session = s

    def _flash_status(self, msg: str, color: int = 2, ms: int = 1200):
        """在底部状态栏短暂显示提示"""
        h, w = self.stdscr.getmaxyx()
        try:
            self.stdscr.addnstr(h - 1, 0, f" {msg} ".ljust(w), w - 1, curses.color_pair(color) | curses.A_BOLD)
            self.stdscr.refresh()
            curses.napms(ms)
        except curses.error:
            pass

    def _do_open_in_terminal(self):
        """在新终端恢复当前选中的会话（不退出 CSM）"""
        if not self.filtered:
            return
        s = self.filtered[self.cursor]
        cmd = store.get_resume_command(s)
        if not cmd:
            self._flash_status("无法获取恢复命令", color=5)
            return

        ok, out = open_in_terminal(cmd, cwd=s.project or "")
        if ok:
            self._flash_status(f"已在新终端恢复: {s.tool_type.label} {s.session_id[:8]}")
        else:
            self._flash_status(f"打开失败: {out[:60] if out else 'unknown'}", color=5, ms=2000)

    def _do_handoff(self):
        """将会话接力到另一工具 — 弹出底部菜单让用户选择目标 CLI"""
        if not self.filtered:
            return
        s = self.filtered[self.cursor]
        h, w = self.stdscr.getmaxyx()

        # 在底部状态栏显示选择菜单
        menu = " 接力到: [1]Claude [2]Codex [3]Gemini [Esc]取消 "
        try:
            self.stdscr.addnstr(h - 1, 0, menu.ljust(w), w - 1,
                                curses.color_pair(6) | curses.A_BOLD)
            self.stdscr.refresh()
        except curses.error:
            pass

        # 临时切到阻塞输入，避免 100ms 轮询导致菜单“闪退”。
        try:
            self.stdscr.timeout(-1)
            key = self.stdscr.getch()
        finally:
            self.stdscr.timeout(100)
        targets = {ord("1"): ToolType.CLAUDE, ord("2"): ToolType.CODEX, ord("3"): ToolType.GEMINI}
        if key not in targets:
            return  # Esc 或其他键 → 取消

        target = targets[key]

        # 优先使用 MCP 接力，fallback 到普通接力
        handoff_fn = open_mcp_handoff_in_terminal or open_handoff_in_terminal
        ok, out = handoff_fn(s, target)
        if ok:
            self._flash_status(f"已接力: {s.tool_type.label} -> {target.label} {s.session_id[:8]}")
        else:
            self._flash_status(f"接力失败: {out[:60] if out else 'unknown'}", color=5, ms=2400)

    def _do_review(self):
        """v 键：按当前审查状态执行下一步（审查/修复/提示）。

        状态机（CSM 本地状态）：
        - "" / pending  -> 打开另一工具进行 review-only 审查，并标记为 pending
        - reviewed      -> 打开原会话（同工具）用于修复/复查
        - rechecked     -> 已完成；新对话会自动重置到未审查
        """

        if not self.filtered:
            return

        s = self.filtered[self.cursor]
        rs = (s.review_status or "").strip().lower()

        # 1) 未审查 / 待审：跳转到另一工具做审查
        if rs in ("", "pending"):
            if s.tool_type == ToolType.CLAUDE:
                target = ToolType.CODEX
            elif s.tool_type == ToolType.CODEX:
                target = ToolType.CLAUDE
            else:
                target = ToolType.CODEX

            # Mark as pending (best-effort) so the list shows the intent.
            ok, out = open_review_in_terminal(s, target)
            if ok:
                # Mark as pending (best-effort) so the list shows the intent.
                try:
                    store.set_session_review_status(s.session_id, s.tool_type, "pending", anchor_ts_ms=int(s.timestamp_end or 0))
                except Exception as e:
                    logger.debug(
                        "failed to set pending review status from TUI: tool=%s session_id=%s error=%s",
                        s.tool_type.label,
                        s.session_id,
                        e,
                    )

                self._flash_status(f"已打开审查: {s.tool_type.label} -> {target.label} {s.session_id[:8]}")

                # Refresh list and keep cursor on the same session.
                prev_sid = s.session_id
                prev_tool = s.tool_type
                self._reload_sessions()
                for i, ss in enumerate(self.filtered):
                    if ss.session_id == prev_sid and ss.tool_type == prev_tool:
                        self.cursor = i
                        break
            else:
                self._flash_status(f"审查失败: {out[:60] if out else 'unknown'}", color=5, ms=2400)

            return

        # 2) 已审查未复查：回到原会话修复并复查
        if rs == "reviewed":
            cmd = store.get_resume_command(s)
            if not cmd:
                self._flash_status("无法获取恢复命令", color=5)
                return

            ok, out = open_in_terminal(cmd, cwd=s.project or "")
            if ok:
                self._flash_status(f"已恢复原会话用于复查: {s.tool_type.label} {s.session_id[:8]}")
            else:
                self._flash_status(f"打开失败: {out[:60] if out else 'unknown'}", color=5, ms=2000)
            return

        # 3) 已复查：提示（新对话会自动重置）
        if rs == "rechecked":
            self._flash_status("已复查：有新对话后会自动回到未审查", color=4, ms=2200)
            return

        # Unknown state: treat as unreviewed.
        self._flash_status("未知审查状态，已按未审处理", color=4, ms=1800)

    def _do_mark_review_done(self):
        """标记当前会话为“已完成审查”（CSM 本地状态）"""

        if not self.filtered:
            return

        s = self.filtered[self.cursor]
        ok, msg = store.set_session_review_status(
            s.session_id,
            s.tool_type,
            "reviewed",
            anchor_ts_ms=int(s.timestamp_end or 0),
        )
        if ok:
            self._flash_status(f"已标记已审: {s.tool_type.label} {s.session_id[:8]}")
        else:
            self._flash_status(f"标记失败: {msg[:60] if msg else 'unknown'}", color=5, ms=2400)

        prev_sid = s.session_id
        prev_tool = s.tool_type
        self._reload_sessions()
        for i, ss in enumerate(self.filtered):
            if ss.session_id == prev_sid and ss.tool_type == prev_tool:
                self.cursor = i
                break

    def _do_mark_recheck_done(self):
        """标记当前会话为“已完成复查/复验”（CSM 本地状态）"""

        if not self.filtered:
            return

        s = self.filtered[self.cursor]
        ok, msg = store.set_session_review_status(
            s.session_id,
            s.tool_type,
            "rechecked",
            anchor_ts_ms=int(s.timestamp_end or 0),
        )
        if ok:
            self._flash_status(f"已标记已复查: {s.tool_type.label} {s.session_id[:8]}")
        else:
            self._flash_status(f"标记失败: {msg[:60] if msg else 'unknown'}", color=5, ms=2400)

        prev_sid = s.session_id
        prev_tool = s.tool_type
        self._reload_sessions()
        for i, ss in enumerate(self.filtered):
            if ss.session_id == prev_sid and ss.tool_type == prev_tool:
                self.cursor = i
                break

    def _do_clear_review_status(self):
        """清除当前会话审查标记（CSM 本地状态）"""

        if not self.filtered:
            return

        s = self.filtered[self.cursor]
        ok, msg = store.set_session_review_status(s.session_id, s.tool_type, "")
        if ok:
            self._flash_status(f"已清除标记: {s.tool_type.label} {s.session_id[:8]}")
        else:
            self._flash_status(f"清除失败: {msg[:60] if msg else 'unknown'}", color=5, ms=2400)

        prev_sid = s.session_id
        prev_tool = s.tool_type
        self._reload_sessions()
        for i, ss in enumerate(self.filtered):
            if ss.session_id == prev_sid and ss.tool_type == prev_tool:
                self.cursor = i
                break

    def _enter_detail(self):
        """进入详情视图"""
        if not self.filtered:
            return
        s = self.filtered[self.cursor]
        self.detail = store.load_session_detail(s.session_id, s.tool_type, s.project)
        if self.detail:
            self.detail_scroll = 0
            self._build_detail_lines()
            self.mode = "detail"

    # ── 详情视图 ──

    def _build_detail_lines(self):
        """构建详情渲染行（缓存，仅进入详情时构建一次）"""
        lines: list[tuple[str, int]] = []
        if not self.detail:
            self._detail_lines = lines
            return

        if self.detail.custom_name:
            lines.append(("", 0))
            lines.append((f"  名称: {self.detail.custom_name}", curses.color_pair(4) | curses.A_BOLD))
            lines.append(("", 0))

        if self.detail.review_status:
            rs = (self.detail.review_status or "").strip().lower()
            if rs == "pending":
                label = "待审 (P)"
                attr = curses.color_pair(5) | curses.A_BOLD
            elif rs == "reviewed":
                label = "已审 (R)"
                attr = curses.color_pair(3) | curses.A_BOLD
            elif rs == "rechecked":
                label = "已复查 (V)"
                attr = curses.color_pair(2) | curses.A_BOLD
            else:
                label = rs
                attr = curses.color_pair(4)

            lines.append((f"  审查状态: {label}", attr))
            lines.append(("", 0))

        # Gemini 加密提示
        if self.detail.tool_type == ToolType.GEMINI and not self.detail.messages:
            lines.append(("", 0))
            lines.append(("  加密会话，无法查看内容", curses.color_pair(5) | curses.A_BOLD))
            lines.append(("  Gemini CLI 使用加密 Protocol Buffer 存储对话", curses.color_pair(4)))
            lines.append(("  可使用 r 键尝试恢复会话", curses.color_pair(4)))
        else:
            for msg in self.detail.messages:
                role_label = "USER" if msg.role == "user" else "ASST"
                color = curses.color_pair(3) if msg.role == "user" else curses.color_pair(7)
                lines.append((f"── {role_label} ──", color | curses.A_BOLD))
                content_lines = msg.content.split("\n")
                for cl in content_lines[:50]:
                    lines.append((cl, color))
                if len(content_lines) > 50:
                    lines.append((f"  ... ({len(content_lines) - 50} 行省略)", curses.color_pair(4)))
                lines.append(("", 0))

        self._detail_lines = lines

    def _draw_detail(self, scr, h, w):
        if not self.detail:
            return

        # 标题
        tag = f"[{self.detail.tool_type.short}] "
        title = f" {tag}"
        if self.detail.custom_name:
            title += f"{self.detail.custom_name} — "
        title += f"会话详情 — {self.detail.session_id[:12]}..."
        if self.detail.cwd:
            title += f"  [{short_project(self.detail.cwd)}]"
        if self.detail.git_branch:
            title += f"  ({self.detail.git_branch})"
        if self.detail.model_provider:
            title += f"  <{self.detail.model_provider}>"
        scr.addnstr(0, 0, truncate(title, w - 1), w - 1, curses.color_pair(1) | curses.A_BOLD)

        lines = self._detail_lines

        # 滚动显示
        view_h = h - 2
        if self.detail_scroll > max(0, len(lines) - view_h):
            self.detail_scroll = max(0, len(lines) - view_h)

        for i in range(view_h):
            li = self.detail_scroll + i
            if li >= len(lines):
                break
            text, attr = lines[li]
            try:
                scr.addnstr(i + 1, 0, truncate(text, w - 1).ljust(w - 1), w - 1, attr)
            except curses.error:
                pass

        # 状态栏
        pos = f"{self.detail_scroll + 1}/{max(1, len(lines))}"
        status = f" j/k:滚动  Space/b:翻页  q:返回  {pos}"
        try:
            scr.addnstr(h - 1, 0, status.ljust(w), w - 1, curses.color_pair(6))
        except curses.error:
            pass

        self._detail_total_lines = len(lines)

    def _handle_detail_key(self, key, h):
        view_h = h - 2
        total = getattr(self, "_detail_total_lines", 0)
        if key in (ord("j"), curses.KEY_DOWN):
            if self.detail_scroll < total - view_h:
                self.detail_scroll += 1
        elif key in (ord("k"), curses.KEY_UP):
            if self.detail_scroll > 0:
                self.detail_scroll -= 1
        elif key == ord(" "):  # 翻页
            self.detail_scroll = min(self.detail_scroll + view_h, max(0, total - view_h))
        elif key == ord("b"):  # 上翻页
            self.detail_scroll = max(0, self.detail_scroll - view_h)
        elif key in (ord("q"), 27):
            self.mode = "list"

    # ── 项目分组视图 ──

    def _enter_group(self):
        self.group_data = store.group_by_project(self.sessions)
        self.group_keys = sorted(self.group_data.keys(), key=lambda k: -len(self.group_data[k]))
        self.group_cursor = 0
        self.group_offset = 0
        self.mode = "group"

    def _draw_group(self, scr, h, w):
        title = f" 按项目分组 — {len(self.group_keys)} 个项目"
        scr.addnstr(0, 0, title, w - 1, curses.color_pair(1) | curses.A_BOLD)

        list_h = h - 3
        if self.group_cursor < self.group_offset:
            self.group_offset = self.group_cursor
        if self.group_cursor >= self.group_offset + list_h:
            self.group_offset = self.group_cursor - list_h + 1

        for i in range(list_h):
            idx = self.group_offset + i
            if idx >= len(self.group_keys):
                break
            proj = self.group_keys[idx]
            count = len(self.group_data[proj])
            is_sel = idx == self.group_cursor
            line = f" {short_project(proj)}  ({count} 个会话)"
            attr = curses.A_REVERSE if is_sel else 0
            try:
                scr.addnstr(i + 1, 0, truncate(line, w - 1).ljust(w - 1), w - 1, attr)
            except curses.error:
                pass

        status = " j/k:移动  Enter:筛选该项目  q:返回"
        try:
            scr.addnstr(h - 1, 0, status.ljust(w), w - 1, curses.color_pair(6))
        except curses.error:
            pass

    def _handle_group_key(self, key, h):
        n = len(self.group_keys)
        if key in (ord("j"), curses.KEY_DOWN):
            if self.group_cursor < n - 1:
                self.group_cursor += 1
        elif key in (ord("k"), curses.KEY_UP):
            if self.group_cursor > 0:
                self.group_cursor -= 1
        elif key in (ord("\n"), curses.KEY_ENTER):
            if self.group_keys:
                proj = self.group_keys[self.group_cursor]
                self.filtered = self.group_data[proj]
                self.search_query = short_project(proj)
                self.cursor = 0
                self.offset = 0
                self.mode = "list"
        elif key in (ord("q"), 27):
            self.mode = "list"

    # ── 统计视图 ──

    def _enter_stats(self):
        self.stats = store.load_stats()
        self.stats_scroll = 0
        self.mode = "stats"

    def _draw_stats(self, scr, h, w):
        title = " 使用统计"
        scr.addnstr(0, 0, title, w - 1, curses.color_pair(1) | curses.A_BOLD)

        lines = []
        if not self.stats:
            lines.append(("  无统计数据", 0))
        else:
            # 每日活动
            daily = self.stats.get("dailyActivity", [])
            if daily:
                lines.append(("  日期        消息数    会话数    工具调用", curses.color_pair(3) | curses.A_BOLD))
                lines.append(("  " + "─" * 44, curses.color_pair(3)))
                for d in daily[-14:]:  # 最近 14 天
                    date = d.get("date", "?")
                    msgs = d.get("messageCount", 0)
                    sess = d.get("sessionCount", 0)
                    tools = d.get("toolCallCount", 0)
                    lines.append((f"  {date}    {msgs:>6}    {sess:>6}    {tools:>6}", 0))
                lines.append(("", 0))

            # Token 使用
            tokens = self.stats.get("dailyModelTokens", [])
            if tokens:
                lines.append(("  Token 使用:", curses.color_pair(4) | curses.A_BOLD))
                lines.append(("  " + "─" * 44, curses.color_pair(4)))
                for t in tokens[-14:]:
                    date = t.get("date", "?")
                    by_model = t.get("tokensByModel", {})
                    for model, count in by_model.items():
                        # 简化模型名
                        short_model = model.replace("claude-", "").replace("-thinking", "")
                        lines.append((f"  {date}  {short_model}: {count:>12,}", 0))

            # 汇总
            lines.append(("", 0))
            lines.append(("  汇总:", curses.color_pair(2) | curses.A_BOLD))
            total_msgs = sum(d.get("messageCount", 0) for d in daily)
            total_sess = sum(d.get("sessionCount", 0) for d in daily)
            total_tools = sum(d.get("toolCallCount", 0) for d in daily)
            lines.append((f"  总消息数: {total_msgs:,}", 0))
            lines.append((f"  总会话数: {total_sess:,}", 0))
            lines.append((f"  总工具调用: {total_tools:,}", 0))

        view_h = h - 2
        for i in range(view_h):
            li = self.stats_scroll + i
            if li >= len(lines):
                break
            text, attr = lines[li]
            try:
                scr.addnstr(i + 1, 0, truncate(text, w - 1).ljust(w - 1), w - 1, attr)
            except curses.error:
                pass

        self._stats_total_lines = len(lines)
        status = " j/k:滚动  q:返回"
        try:
            scr.addnstr(h - 1, 0, status.ljust(w), w - 1, curses.color_pair(6))
        except curses.error:
            pass

    def _handle_stats_key(self, key, h):
        view_h = h - 2
        total = getattr(self, "_stats_total_lines", 0)
        if key in (ord("j"), curses.KEY_DOWN):
            if self.stats_scroll < total - view_h:
                self.stats_scroll += 1
        elif key in (ord("k"), curses.KEY_UP):
            if self.stats_scroll > 0:
                self.stats_scroll -= 1
        elif key in (ord("q"), 27):
            self.mode = "list"

    # ── 帮助视图 ──

    def _draw_help(self, scr, h, w):
        title = " 帮助 — 快捷键"
        scr.addnstr(0, 0, title, w - 1, curses.color_pair(1) | curses.A_BOLD)

        help_lines = [
            "",
            "  列表视图:",
            "    j / ↓        下移",
            "    k / ↑        上移",
            "    g            跳到顶部",
            "    G            跳到底部",
            "    Space        向下翻页",
            "    b            向上翻页",
            "    Ctrl+D       向下半页",
            "    Ctrl+U       向上半页",
            "    Enter        查看会话详情",
            "    /            搜索会话（支持中文）",
            "    Tab          切换工具筛选（全部/Claude Code/CodeX/Gemini）",
            "    d            删除会话（需确认）",
            "    r            恢复会话",
            "    o            在新终端恢复会话（不退出 CSM）",
            "    x            接力到另一工具（基于 handoff 快照）",
            "    v            审查流程下一步（未审->审查；已审->复查）",
            "    R            标记为已完成审查（CSM 本地状态）",
            "    V            标记为已完成复查/复验（CSM 本地状态）",
            "    U            清除审查标记（CSM 本地状态）",
            "    n            修改会话名称（命名输入可配置）",
            "                 CSM_TUI_NAME_INPUT=terminal|dialog|curses  (默认 terminal)",
            "    p            按项目分组",
            "    s            查看使用统计",
            "    ?            显示帮助",
            "    q / ESC      退出",
            "",
            "  详情视图:",
            "    j / ↓        向下滚动",
            "    k / ↑        向上滚动",
            "    Space        向下翻页",
            "    b            向上翻页",
            "    q / ESC      返回列表",
            "",
            "  工具标识:",
            "    [Claude Code]  [CodeX]  [Gemini]",
            "  审查标记:",
            "    P = 待审    R = 已审    V = 已复查（仅 CSM 本地标记）",
        ]

        for i, line in enumerate(help_lines):
            if i + 1 >= h - 1:
                break
            try:
                scr.addnstr(i + 1, 0, line, w - 1)
            except curses.error:
                pass

        status = " q:返回"
        try:
            scr.addnstr(h - 1, 0, status.ljust(w), w - 1, curses.color_pair(6))
        except curses.error:
            pass
