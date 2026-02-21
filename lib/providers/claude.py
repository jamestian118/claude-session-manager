"""Claude Code provider — 从 ~/.claude/ 读取会话数据"""

import json
import os
import re
import shutil
import time
from pathlib import Path
from .base import BaseProvider
from ..models import ToolType, SessionSummary, SessionDetail, ChatMessage


class ClaudeProvider(BaseProvider):

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CLAUDE

    @property
    def base_dir(self) -> Path:
        return Path.home() / ".claude"

    @property
    def _history_file(self) -> Path:
        return self.base_dir / "history.jsonl"

    @property
    def _projects_dir(self) -> Path:
        return self.base_dir / "projects"

    @property
    def _session_env_dir(self) -> Path:
        return self.base_dir / "session-env"

    @property
    def _stats_file(self) -> Path:
        return self.base_dir / "stats-cache.json"

    # ── 会话列表 ──

    @staticmethod
    def _decode_project_dir(dirname: str) -> str:
        """将编码的项目目录名还原为路径，如 -Users-Zhuanz-Documents-Code -> $HOME/Documents/Code"""
        if dirname.startswith("-"):
            return "/" + dirname[1:].replace("-", "/")
        return dirname.replace("-", "/")

    @staticmethod
    def _parse_iso_ts(ts_str: str) -> float:
        """ISO 8601 时间戳转毫秒 epoch"""
        if not ts_str:
            return 0
        try:
            from datetime import datetime, timezone
            # 处理 Z 结尾和 +00:00 格式
            s = ts_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt.timestamp() * 1000
        except (ValueError, OSError):
            return 0

    def _scan_session_file(self, jsonl_path: Path) -> dict | None:
        """扫描会话 JSONL 文件前部，提取元数据"""
        sid = jsonl_path.stem
        first_ts = 0.0
        last_ts = 0.0
        cwd = ""
        first_user_text = ""
        user_msg_count = 0
        total_msg_count = 0

        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    rec_type = rec.get("type", "")

                    # 提取时间戳（ISO 格式）
                    ts_raw = rec.get("timestamp", "")
                    if isinstance(ts_raw, str):
                        ts = self._parse_iso_ts(ts_raw)
                    elif isinstance(ts_raw, (int, float)):
                        ts = float(ts_raw)
                    else:
                        ts = 0

                    if ts and not first_ts:
                        first_ts = ts
                    if ts:
                        last_ts = ts

                    if rec_type == "user":
                        user_msg_count += 1
                        total_msg_count += 1
                        if not cwd:
                            cwd = rec.get("cwd", "")
                        # 提取首条用户消息内容
                        if not first_user_text:
                            # Skip meta/system-like user records (they are not good session titles).
                            if rec.get("isMeta") is True:
                                continue
                            msg = rec.get("message", {})
                            content = msg.get("content", "")
                            if isinstance(content, str):
                                text = content.strip()
                            elif isinstance(content, list):
                                parts = []
                                for bl in content:
                                    if isinstance(bl, dict) and bl.get("type") == "text":
                                        parts.append(bl.get("text", ""))
                                text = "\n".join(parts).strip()
                            else:
                                text = ""
                            if not text:
                                continue

                            # Best-effort: strip XML-ish wrappers produced by Claude Code UI.
                            # Example: <command-name>/model</command-name> ...
                            candidate = text.strip()
                            if candidate.startswith("<"):
                                candidate = re.sub(r"</?[^>]+>", "", candidate).strip()
                            # Strip ANSI escape sequences (color/style) which are not useful for titles.
                            candidate = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", candidate).strip()

                            # Skip IDE/context and local-command wrappers.
                            if candidate.startswith("<ide_") or candidate.startswith("<local-command") or candidate.startswith("<command-"):
                                continue

                            # Skip slash-commands like /model, /status, etc.
                            # This makes session titles more likely to be the first "real" user prompt.
                            if candidate.startswith("/") or candidate.lower() in ("exit", "quit"):
                                continue
                            if candidate.lower().startswith("caveat:"):
                                continue

                            # 跳过 IDE 上下文标签，提取真实内容
                            if candidate and not candidate.startswith("<ide_") and not candidate.startswith("<local-command"):
                                first_user_text = candidate[:200]
                    elif rec_type == "assistant":
                        total_msg_count += 1
        except OSError:
            return None

        # 跳过无消息的空会话
        if total_msg_count == 0:
            return None

        # 使用文件修改时间作为 fallback
        if not last_ts:
            try:
                last_ts = jsonl_path.stat().st_mtime * 1000
            except OSError:
                pass
        if not first_ts:
            first_ts = last_ts

        return {
            "session_id": sid,
            "project": cwd,
            "first_display": first_user_text,
            "last_display": first_user_text,
            "timestamp_start": first_ts,
            "timestamp_end": last_ts,
            "message_count": total_msg_count,
            "tool_type": ToolType.CLAUDE,
        }

    def load_sessions(self) -> list[SessionSummary]:
        agg: dict[str, dict] = {}

        # 1. 从 history.jsonl 加载（CLI 会话的输入记录）
        if self._history_file.exists():
            with open(self._history_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sid = rec.get("sessionId", "")
                    if not sid:
                        continue
                    ts = rec.get("timestamp", 0)
                    display = rec.get("display", "").strip()
                    project = rec.get("project", "")

                    if sid not in agg:
                        agg[sid] = {
                            "session_id": sid,
                            "project": project,
                            "first_display": display,
                            "last_display": display,
                            "timestamp_start": ts,
                            "timestamp_end": ts,
                            "message_count": 1,
                            "tool_type": ToolType.CLAUDE,
                        }
                    else:
                        entry = agg[sid]
                        entry["message_count"] += 1
                        entry["last_display"] = display
                        if ts < entry["timestamp_start"]:
                            entry["timestamp_start"] = ts
                            entry["first_display"] = display
                        if ts > entry["timestamp_end"]:
                            entry["timestamp_end"] = ts

        # 2. 扫描 projects 目录，发现所有会话（包括 VSCode/IDE 创建的）
        if self._projects_dir.exists():
            for project_dir in self._projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                for jsonl_file in project_dir.glob("*.jsonl"):
                    sid = jsonl_file.stem
                    if sid in agg:
                        continue  # 已从 history.jsonl 中加载过
                    meta = self._scan_session_file(jsonl_file)
                    if meta:
                        # 如果未能从文件中获取 project，从目录名解码
                        if not meta["project"]:
                            meta["project"] = self._decode_project_dir(project_dir.name)
                        agg[sid] = meta

        sessions = [SessionSummary(**v) for v in agg.values()]
        sessions.sort(key=lambda s: s.timestamp_end, reverse=True)
        return sessions

    # ── 会话详情 ──

    def _find_session_jsonl(self, session_id: str) -> Path | None:
        if not self._projects_dir.exists():
            return None
        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            jsonl = project_dir / f"{session_id}.jsonl"
            if jsonl.exists():
                return jsonl
        return None

    def load_session_detail(self, session_id: str, project: str = "") -> SessionDetail | None:
        jsonl_path = self._find_session_jsonl(session_id)
        if not jsonl_path:
            return None

        detail = SessionDetail(
            session_id=session_id, project=project,
            tool_type=ToolType.CLAUDE,
        )
        messages: list[ChatMessage] = []
        files_set: set[str] = set()
        cmds_set: set[str] = set()
        errors_list: list[str] = []

        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rec_type = rec.get("type", "")
                if rec_type not in ("user", "assistant"):
                    continue

                if not detail.cwd and rec.get("cwd"):
                    detail.cwd = rec["cwd"]
                if not detail.git_branch and rec.get("gitBranch"):
                    detail.git_branch = rec["gitBranch"]

                msg_data = rec.get("message", {})
                role = msg_data.get("role", rec_type)
                content_raw = msg_data.get("content", "")

                if isinstance(content_raw, str):
                    text = content_raw
                elif isinstance(content_raw, list):
                    parts = []
                    for block in content_raw:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type", "")
                        if btype == "text":
                            parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            name = block.get("name", "tool")
                            parts.append(f"[调用工具: {name}]")
                            # 提取文件变更和命令
                            inp = block.get("input", {})
                            if name in ("Edit", "Write") and inp.get("file_path"):
                                files_set.add(inp["file_path"])
                            elif name == "Bash" and inp.get("command"):
                                cmds_set.add(inp["command"])
                        elif btype == "tool_result":
                            # 提取错误信息
                            is_err = block.get("is_error", False)
                            tr_content = block.get("content", "")
                            if isinstance(tr_content, list):
                                tr_content = " ".join(
                                    b.get("text", "") for b in tr_content if isinstance(b, dict)
                                )
                            if is_err or (isinstance(tr_content, str) and
                                          ("error" in tr_content.lower() or "Error" in tr_content)):
                                if isinstance(tr_content, str) and tr_content.strip():
                                    errors_list.append(tr_content.strip()[:200])
                            parts.append("[工具结果]")
                    text = "\n".join(parts)
                else:
                    text = str(content_raw)

                text = text.strip()
                if not text:
                    continue

                messages.append(ChatMessage(
                    role=role,
                    content=text,
                    timestamp=rec.get("timestamp", ""),
                    uuid=rec.get("uuid", ""),
                ))

        detail.messages = messages
        detail.files_changed = list(files_set)[-50:]
        detail.commands_run = list(cmds_set)[-30:]
        detail.errors = errors_list[-20:]
        return detail

    # ── 删除 ──

    def delete_session(self, session_id: str) -> dict[str, bool]:
        result = {"jsonl": False, "subagents": False, "env": False, "history": False}

        jsonl_path = self._find_session_jsonl(session_id)
        if jsonl_path and jsonl_path.exists():
            # 同时清理对应的 subagents 目录
            subagents_dir = jsonl_path.parent / session_id
            if subagents_dir.exists():
                shutil.rmtree(subagents_dir)
                result["subagents"] = True
            jsonl_path.unlink()
            result["jsonl"] = True

        env_dir = self._session_env_dir / session_id
        if env_dir.exists():
            shutil.rmtree(env_dir)
            result["env"] = True

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
                        if rec.get("sessionId") == session_id:
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

        return result

    # ── 恢复 ──

    def get_resume_command(self, session_id: str) -> list[str]:
        return ["claude", "--resume", session_id]

    # ── 会话名称 / 标题（尽力写入 Claude 的本地历史） ──

    def _rewrite_history_first_display(self, session_id: str, new_display: str) -> tuple[bool, str]:
        """Rewrite the earliest history entry's display for a given sessionId.

        Claude Code session listing typically derives a short label from history.jsonl. There isn't a
        stable cross-tool "rename API", so we do a best-effort rewrite of the first display string.
        """
        if not self._history_file.exists():
            return False, "history.jsonl not found"

        cleaned = " ".join((new_display or "").split()).strip()
        if not cleaned:
            return False, "Empty title"

        # Pass 1: find earliest timestamp for this session.
        min_ts: int | None = None
        try:
            with open(self._history_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("sessionId") != session_id:
                        continue
                    ts = rec.get("timestamp")
                    if not isinstance(ts, int):
                        continue
                    if min_ts is None or ts < min_ts:
                        min_ts = ts
        except OSError as e:
            return False, f"Failed to read history.jsonl: {e}"

        if min_ts is None:
            return False, "Session not found in history.jsonl"

        # Pass 2: rewrite file (atomic replace).
        bak = self._history_file.with_suffix(self._history_file.suffix + f".bak.{int(time.time())}")
        tmp = self._history_file.with_suffix(self._history_file.suffix + ".tmp")
        try:
            st = self._history_file.stat()
            mode = st.st_mode & 0o777
        except OSError:
            mode = 0o600

        try:
            shutil.copy2(self._history_file, bak)
        except OSError:
            # Backup is best-effort; continue.
            pass

        changed = False
        try:
            with open(self._history_file, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
                for line in src:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        rec = json.loads(stripped)
                    except json.JSONDecodeError:
                        # Keep corrupt lines as-is (rare).
                        dst.write(stripped + "\n")
                        continue

                    if rec.get("sessionId") == session_id and rec.get("timestamp") == min_ts:
                        rec["display"] = cleaned
                        dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        changed = True
                    else:
                        dst.write(stripped + "\n")

            os.chmod(tmp, mode)
            os.replace(tmp, self._history_file)
        except OSError as e:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False, f"Failed to rewrite history.jsonl: {e}"

        if not changed:
            return False, "No matching history entry updated"
        return True, "OK"

    def get_session_title(self, session_id: str) -> str | None:
        if not self._history_file.exists():
            return None
        min_ts: int | None = None
        best: str | None = None
        try:
            with open(self._history_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("sessionId") != session_id:
                        continue
                    ts = rec.get("timestamp")
                    if not isinstance(ts, int):
                        continue
                    disp = rec.get("display", "")
                    if not isinstance(disp, str):
                        continue
                    if min_ts is None or ts < min_ts:
                        min_ts = ts
                        best = disp.strip()
        except OSError:
            return None
        return best or None

    def set_session_title(self, session_id: str, title: str) -> tuple[bool, str]:
        return self._rewrite_history_first_display(session_id, title)

    def clear_session_title(self, session_id: str) -> tuple[bool, str]:
        # Best-effort: restore a default-ish title from the session JSONL itself.
        jsonl_path = self._find_session_jsonl(session_id)
        if not jsonl_path or not jsonl_path.exists():
            return False, "Session JSONL not found"
        meta = self._scan_session_file(jsonl_path)
        if not meta:
            return False, "Failed to infer default title from session JSONL"
        default_title = (meta.get("first_display") or "").strip()
        if not default_title:
            return False, "Default title is empty"
        return self._rewrite_history_first_display(session_id, default_title)

    # ── 统计 ──

    def load_stats(self) -> dict | None:
        if not self._stats_file.exists():
            return None
        try:
            with open(self._stats_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
