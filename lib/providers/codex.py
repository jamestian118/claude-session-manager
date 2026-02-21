"""Codex CLI provider — 从 ~/.codex/ 读取会话数据"""

import json
import os
import sqlite3
from pathlib import Path
from .base import BaseProvider
from ..models import ToolType, SessionSummary, SessionDetail, ChatMessage


class CodexProvider(BaseProvider):

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CODEX

    @property
    def base_dir(self) -> Path:
        return Path.home() / ".codex"

    @property
    def _history_file(self) -> Path:
        return self.base_dir / "history.jsonl"

    @property
    def _sessions_dir(self) -> Path:
        return self.base_dir / "sessions"

    @property
    def _archived_dir(self) -> Path:
        return self.base_dir / "archived_sessions"

    # ── 会话列表 ──

    def load_sessions(self) -> list[SessionSummary]:
        sessions_from_history = self._load_from_history()
        sessions_from_files = self._load_from_session_files()
        sessions_from_sqlite = self._load_from_sqlite()

        # 合并：history 优先，文件补充，SQLite 兜底
        seen = {s.session_id for s in sessions_from_history}
        merged = sessions_from_history[:]
        for s in sessions_from_files:
            if s.session_id not in seen:
                merged.append(s)
                seen.add(s.session_id)
        for s in sessions_from_sqlite:
            if s.session_id not in seen:
                merged.append(s)
                seen.add(s.session_id)

        merged.sort(key=lambda s: s.timestamp_end, reverse=True)
        return merged

    def _load_from_history(self) -> list[SessionSummary]:
        """从 history.jsonl 聚合"""
        if not self._history_file.exists():
            return []

        agg: dict[str, dict] = {}
        with open(self._history_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = rec.get("session_id", "")
                if not sid:
                    continue
                # Codex history 时间戳是秒，转毫秒
                ts = rec.get("ts", 0) * 1000
                text = rec.get("text", "").strip()

                if sid not in agg:
                    agg[sid] = {
                        "session_id": sid,
                        "project": "",
                        "first_display": text,
                        "last_display": text,
                        "timestamp_start": ts,
                        "timestamp_end": ts,
                        "message_count": 1,
                        "tool_type": ToolType.CODEX,
                    }
                else:
                    entry = agg[sid]
                    entry["message_count"] += 1
                    entry["last_display"] = text
                    if ts < entry["timestamp_start"]:
                        entry["timestamp_start"] = ts
                        entry["first_display"] = text
                    if ts > entry["timestamp_end"]:
                        entry["timestamp_end"] = ts

        return [SessionSummary(**v) for v in agg.values()]

    def _load_from_session_files(self) -> list[SessionSummary]:
        """扫描 sessions/ 和 archived_sessions/ 补充"""
        results = []
        for d in (self._sessions_dir, self._archived_dir):
            if not d.exists():
                continue
            for jsonl in d.rglob("*.jsonl"):
                try:
                    summary = self._parse_session_file_summary(jsonl)
                    if summary:
                        results.append(summary)
                except Exception:
                    continue
        return results

    def _load_from_sqlite(self) -> list[SessionSummary]:
        """从 SQLite 数据库 threads 表中加载（兜底补充）"""
        db_path = self._find_state_db()
        if not db_path:
            return []
        results = []
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute(
                "SELECT id, title, cwd, created_at, updated_at, first_user_message "
                "FROM threads ORDER BY updated_at DESC"
            )
            for row in cur.fetchall():
                sid, title, cwd, created_at, updated_at, first_msg = row
                # SQLite 时间戳是秒，转毫秒
                ts_start = (created_at * 1000) if created_at < 1e12 else created_at
                ts_end = (updated_at * 1000) if updated_at < 1e12 else updated_at
                # title 可能是多行的，取第一行作为显示
                display = (first_msg or title or "").split("\n")[0].strip()
                results.append(SessionSummary(
                    session_id=sid,
                    project=cwd or "",
                    first_display=display,
                    last_display=display,
                    timestamp_start=ts_start,
                    timestamp_end=ts_end,
                    message_count=1,
                    tool_type=ToolType.CODEX,
                ))
            conn.close()
        except Exception:
            pass
        return results

    def _parse_session_file_summary(self, path: Path) -> SessionSummary | None:
        """从会话文件中提取摘要信息"""
        session_id = ""
        first_user_msg = ""
        last_user_msg = ""
        ts_start = 0.0
        ts_end = 0.0
        msg_count = 0
        cwd = ""

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rec_type = rec.get("type", "")
                payload = rec.get("payload", {})

                if rec_type == "session_meta":
                    session_id = payload.get("id", "")
                    cwd = payload.get("cwd", "")
                    # ISO 时间戳转毫秒
                    ts_str = payload.get("timestamp", "")
                    if ts_str:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            ts_start = dt.timestamp() * 1000
                        except (ValueError, OSError):
                            pass

                elif rec_type == "response_item":
                    if payload.get("type") == "message" and payload.get("role") == "user":
                        msg_count += 1
                        content = payload.get("content", [])
                        text = ""
                        for block in content:
                            if isinstance(block, dict) and block.get("type") in ("input_text", "text"):
                                text = block.get("text", "")
                                break
                        if text:
                            if not first_user_msg:
                                first_user_msg = text
                            last_user_msg = text

                    # 更新时间戳
                    rec_ts = rec.get("timestamp")
                    if rec_ts:
                        ts_ms = rec_ts * 1000 if rec_ts < 1e12 else rec_ts
                        if ts_start == 0 or ts_ms < ts_start:
                            ts_start = ts_ms
                        if ts_ms > ts_end:
                            ts_end = ts_ms

        if not session_id:
            # 从文件名提取
            session_id = path.stem

        if ts_end == 0:
            ts_end = ts_start or path.stat().st_mtime * 1000

        return SessionSummary(
            session_id=session_id,
            project=cwd,
            first_display=first_user_msg,
            last_display=last_user_msg or first_user_msg,
            timestamp_start=ts_start,
            timestamp_end=ts_end,
            message_count=max(msg_count, 1),
            tool_type=ToolType.CODEX,
        )

    # ── 查找会话文件 ──

    def _find_session_file(self, session_id: str) -> Path | None:
        for d in (self._sessions_dir, self._archived_dir):
            if not d.exists():
                continue
            matches = list(d.rglob(f"*{session_id}.jsonl"))
            if matches:
                return matches[0]
        return None

    # ── 会话详情 ──

    def load_session_detail(self, session_id: str, project: str = "") -> SessionDetail | None:
        path = self._find_session_file(session_id)
        if not path:
            return None

        detail = SessionDetail(
            session_id=session_id, project=project,
            tool_type=ToolType.CODEX,
        )
        messages: list[ChatMessage] = []
        files_set: set[str] = set()
        cmds_set: set[str] = set()
        errors_list: list[str] = []

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rec_type = rec.get("type", "")
                payload = rec.get("payload", {})

                if rec_type == "session_meta":
                    detail.cwd = payload.get("cwd", "")
                    detail.model_provider = payload.get("model_provider", "")
                    continue

                if rec_type != "response_item":
                    continue

                p_type = payload.get("type", "")
                role = payload.get("role", "")

                # 提取 function_call 工具调用信息
                if p_type == "function_call":
                    name = payload.get("name", "")
                    args_str = payload.get("arguments", "")
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    if name in ("Edit", "Write") and args.get("file_path"):
                        files_set.add(args["file_path"])
                    elif name == "Bash" and args.get("command"):
                        cmds_set.add(args["command"])
                    continue

                # 提取 function_call_output 中的错误
                if p_type == "function_call_output":
                    output = payload.get("output", "")
                    if isinstance(output, str) and (
                        "error" in output.lower() or "Error" in output
                    ):
                        errors_list.append(output.strip()[:200])
                    continue

                if p_type != "message":
                    continue
                if role not in ("user", "assistant"):
                    continue

                content = payload.get("content", [])
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype in ("input_text", "output_text", "text"):
                            parts.append(block.get("text", ""))
                text = "\n".join(parts).strip()
                if not text:
                    continue

                ts = str(rec.get("timestamp", ""))
                messages.append(ChatMessage(role=role, content=text, timestamp=ts))

        detail.messages = messages
        detail.files_changed = list(files_set)[-50:]
        detail.commands_run = list(cmds_set)[-30:]
        detail.errors = errors_list[-20:]
        return detail

    # ── 内部属性 ──

    @property
    def _shell_snapshots_dir(self) -> Path:
        return self.base_dir / "shell_snapshots"

    @property
    def _global_state_file(self) -> Path:
        return self.base_dir / ".codex-global-state.json"

    @property
    def _dev_db_file(self) -> Path:
        return self.base_dir / "sqlite" / "codex-dev.db"

    def _find_state_db(self) -> Path | None:
        """查找 Codex 主 SQLite 数据库 (state_*.sqlite)"""
        candidates = sorted(self.base_dir.glob("state_*.sqlite"), reverse=True)
        return candidates[0] if candidates else None

    # ── 删除 ──

    def delete_session(self, session_id: str) -> dict[str, bool]:
        result = {
            "session_file": False,
            "history": False,
            "sqlite_thread": False,
            "sqlite_logs": False,
            "shell_snapshot": False,
            "global_state": False,
            "dev_db": False,
        }

        # 1. 删除会话 JSONL 文件
        path = self._find_session_file(session_id)
        if path and path.exists():
            path.unlink()
            result["session_file"] = True

        # 2. 从 history.jsonl 中移除
        if self._history_file.exists():
            lines_to_keep = []
            removed = False
            with open(self._history_file, encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        rec = json.loads(stripped)
                        if rec.get("session_id") == session_id:
                            removed = True
                            continue
                    except json.JSONDecodeError:
                        pass
                    lines_to_keep.append(stripped)
            if removed:
                with open(self._history_file, "w", encoding="utf-8") as f:
                    for l in lines_to_keep:
                        f.write(l + "\n")
                result["history"] = True

        # 3. 从 SQLite 数据库中删除 thread 记录
        #    threads 表是 Codex 的主要会话注册中心
        #    thread_dynamic_tools / stage1_outputs 通过 ON DELETE CASCADE 自动清理
        db_path = self._find_state_db()
        if db_path and db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cur = conn.cursor()

                # 删除 logs（无 CASCADE，需手动）
                cur.execute("DELETE FROM logs WHERE thread_id = ?", (session_id,))
                if cur.rowcount > 0:
                    result["sqlite_logs"] = True

                # 删除 threads（CASCADE 会清理 thread_dynamic_tools, stage1_outputs）
                cur.execute("DELETE FROM threads WHERE id = ?", (session_id,))
                if cur.rowcount > 0:
                    result["sqlite_thread"] = True

                conn.commit()
                conn.close()
            except Exception:
                pass

        # 4. 删除 shell_snapshots 文件
        snapshot = self._shell_snapshots_dir / f"{session_id}.sh"
        if snapshot.exists():
            snapshot.unlink()
            result["shell_snapshot"] = True

        # 5. 清理 .codex-global-state.json 中的 thread-titles
        if self._global_state_file.exists():
            try:
                with open(self._global_state_file, encoding="utf-8") as f:
                    state = json.load(f)

                modified = False
                # thread-titles.titles 字典
                titles = state.get("thread-titles", {})
                titles_map = titles.get("titles", {})
                if session_id in titles_map:
                    del titles_map[session_id]
                    modified = True

                # thread-titles.order 列表
                order = titles.get("order", [])
                if session_id in order:
                    order.remove(session_id)
                    modified = True

                # queued-follow-ups 可能引用 session
                follow_ups = state.get("queued-follow-ups", {})
                if session_id in follow_ups:
                    del follow_ups[session_id]
                    modified = True

                if modified:
                    with open(self._global_state_file, "w", encoding="utf-8") as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
                    result["global_state"] = True
            except Exception:
                pass

        # 6. 清理 codex-dev.db 中的关联记录
        if self._dev_db_file.exists():
            try:
                conn = sqlite3.connect(str(self._dev_db_file))
                cur = conn.cursor()
                changed = False

                # inbox_items 可能关联 thread_id
                cur.execute("DELETE FROM inbox_items WHERE thread_id = ?", (session_id,))
                if cur.rowcount > 0:
                    changed = True

                # automation_runs 以 thread_id 为主键
                cur.execute("DELETE FROM automation_runs WHERE thread_id = ?", (session_id,))
                if cur.rowcount > 0:
                    changed = True

                conn.commit()
                conn.close()
                if changed:
                    result["dev_db"] = True
            except Exception:
                pass

        return result

    # ── 恢复 ──

    def get_resume_command(self, session_id: str) -> list[str]:
        return [self._find_multitool_codex(), "resume", session_id]

    @staticmethod
    def _find_multitool_codex() -> str:
        """找到支持 resume 子命令的完整版 codex binary。

        codex 有两种 binary：
        - codex-tui：仅 TUI，不含 resume 等子命令
        - codex (multitool)：完整版，包含 resume/fork/exec 等子命令

        用户的 PATH 中可能优先指向 codex-tui（如自编译版本），
        这里按优先级查找完整版。
        """
        import shutil
        import subprocess

        # 优先：Homebrew 安装的完整版
        brew_path = "/opt/homebrew/bin/codex"
        if os.path.isfile(brew_path) and os.access(brew_path, os.X_OK):
            return brew_path

        # 其次：PATH 中的 codex，检查是否支持 resume 子命令
        codex_path = shutil.which("codex")
        if codex_path:
            try:
                result = subprocess.run(
                    [codex_path, "resume", "--help"],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0:
                    return codex_path
            except (OSError, subprocess.TimeoutExpired):
                pass

        # 兜底：直接用 codex，让系统 PATH 解析
        return "codex"

    # ── 会话名称 / 标题（尽力写入 Codex 的本地状态） ──

    def get_session_title(self, session_id: str) -> str | None:
        db_path = self._find_state_db()
        if not db_path or not db_path.exists():
            return None
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT title FROM threads WHERE id = ?", (session_id,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            title = row[0]
            if isinstance(title, str) and title.strip():
                return title
        except Exception:
            return None
        return None

    def _update_global_state_title(self, session_id: str, title: str) -> tuple[bool, str]:
        """Best-effort update of ~/.codex/.codex-global-state.json thread titles."""
        if not self._global_state_file.exists():
            return False, "global state file not found"
        try:
            with open(self._global_state_file, encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                return False, "invalid global state json"

            tt = state.get("thread-titles")
            if not isinstance(tt, dict):
                tt = {}
                state["thread-titles"] = tt
            titles_map = tt.get("titles")
            if not isinstance(titles_map, dict):
                titles_map = {}
                tt["titles"] = titles_map
            order = tt.get("order")
            if not isinstance(order, list):
                order = []
                tt["order"] = order

            titles_map[session_id] = title
            if session_id not in order:
                order.append(session_id)

            tmp = self._global_state_file.with_suffix(self._global_state_file.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._global_state_file)
            return True, "OK"
        except Exception as e:
            return False, f"failed: {e}"

    def _clear_global_state_title(self, session_id: str) -> tuple[bool, str]:
        if not self._global_state_file.exists():
            return False, "global state file not found"
        try:
            with open(self._global_state_file, encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                return False, "invalid global state json"

            tt = state.get("thread-titles")
            if not isinstance(tt, dict):
                return True, "OK (no thread-titles)"
            titles_map = tt.get("titles")
            order = tt.get("order")

            modified = False
            if isinstance(titles_map, dict) and session_id in titles_map:
                del titles_map[session_id]
                modified = True
            if isinstance(order, list) and session_id in order:
                order.remove(session_id)
                modified = True

            if not modified:
                return True, "OK (no-op)"

            tmp = self._global_state_file.with_suffix(self._global_state_file.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._global_state_file)
            return True, "OK"
        except Exception as e:
            return False, f"failed: {e}"

    def set_session_title(self, session_id: str, title: str) -> tuple[bool, str]:
        cleaned = " ".join((title or "").split()).strip()
        if not cleaned:
            return False, "Empty title"

        db_path = self._find_state_db()
        if not db_path or not db_path.exists():
            return False, "Codex state sqlite not found"

        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute(
                "UPDATE threads SET title = ? WHERE id = ?",
                (cleaned, session_id),
            )
            changed = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
            conn.close()
        except Exception as e:
            return False, f"Failed to update sqlite title: {e}"

        if changed <= 0:
            return False, "Thread not found in sqlite"

        # Best-effort: update the global state title map if present.
        self._update_global_state_title(session_id, cleaned)
        return True, "note: codex resume picker 'Conversation' is derived from prompts and may not reflect renames"

    def clear_session_title(self, session_id: str) -> tuple[bool, str]:
        """Restore a default-ish title by inferring it from the rollout JSONL when available."""
        db_path = self._find_state_db()
        if not db_path or not db_path.exists():
            return False, "Codex state sqlite not found"

        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT rollout_path, first_user_message, title FROM threads WHERE id = ?", (session_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return False, "Thread not found in sqlite"

            rollout_path, first_user_message, current_title = row

            default = ""
            if isinstance(rollout_path, str) and rollout_path.strip():
                p = Path(rollout_path)
                if p.exists():
                    summary = self._parse_session_file_summary(p)
                    if summary:
                        default = (summary.first_display or "").strip()
            if not default:
                default = (first_user_message or "").strip() if isinstance(first_user_message, str) else ""
            if not default:
                # If we cannot infer a default, keep the current title but still clear global override.
                conn.close()
                self._clear_global_state_title(session_id)
                return True, "OK (no default title found; kept sqlite title)"

            cur.execute(
                "UPDATE threads SET title = ? WHERE id = ?",
                (default, session_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            return False, f"Failed to restore sqlite title: {e}"

        # Best-effort: clear global state override.
        self._clear_global_state_title(session_id)
        return True, "OK"
