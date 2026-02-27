"""Gemini CLI provider — 从 ~/.gemini/ 读取会话数据（受限支持）"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from .base import BaseProvider
from ..models import ToolType, SessionSummary, SessionDetail


class GeminiProvider(BaseProvider):

    @property
    def tool_type(self) -> ToolType:
        return ToolType.GEMINI

    @property
    def base_dir(self) -> Path:
        return Path.home() / ".gemini"

    @property
    def _conversations_dir(self) -> Path:
        return self.base_dir / "antigravity" / "conversations"

    @property
    def _annotations_dir(self) -> Path:
        return self.base_dir / "antigravity" / "annotations"

    def is_available(self) -> bool:
        return self._conversations_dir.exists() and shutil.which("gemini") is not None

    # ── 会话列表 ──

    def load_sessions(self) -> list[SessionSummary]:
        if not self._conversations_dir.exists():
            return []

        sessions = []
        for pb_file in self._conversations_dir.glob("*.pb"):
            uuid = pb_file.stem
            ts = self._get_annotation_timestamp(uuid)
            if ts == 0:
                # 回退到文件修改时间
                ts = pb_file.stat().st_mtime * 1000

            sessions.append(SessionSummary(
                session_id=uuid,
                project="",
                first_display="(加密会话)",
                last_display="(加密会话)",
                timestamp_start=ts,
                timestamp_end=ts,
                message_count=0,
                tool_type=ToolType.GEMINI,
            ))

        sessions.sort(key=lambda s: s.timestamp_end, reverse=True)
        return sessions

    def _get_annotation_timestamp(self, uuid: str) -> float:
        """从 annotation pbtxt 解析时间戳"""
        pbtxt = self._annotations_dir / f"{uuid}.pbtxt"
        if not pbtxt.exists():
            return 0
        try:
            text = pbtxt.read_text(encoding="utf-8", errors="replace")
            # 匹配 last_user_view_time { seconds: 1234567890 }
            m = re.search(r"seconds:\s*(\d+)", text)
            if m:
                return int(m.group(1)) * 1000
        except OSError:
            pass
        return 0

    # ── 会话详情（加密，无法读取） ──

    def load_session_detail(self, session_id: str, project: str = "") -> SessionDetail | None:
        pb_file = self._conversations_dir / f"{session_id}.pb"
        if not pb_file.exists():
            return None
        # 加密 Protocol Buffer，无法读取内容
        return SessionDetail(
            session_id=session_id,
            project=project,
            messages=[],
            tool_type=ToolType.GEMINI,
        )

    # ── 删除 ──

    def delete_session(self, session_id: str) -> dict[str, bool]:
        result = {"conversation": False, "annotation": False}

        pb_file = self._conversations_dir / f"{session_id}.pb"
        if pb_file.exists():
            pb_file.unlink()
            result["conversation"] = True

        pbtxt = self._annotations_dir / f"{session_id}.pbtxt"
        if pbtxt.exists():
            pbtxt.unlink()
            result["annotation"] = True

        return result

    # ── 恢复（受限） ──

    def get_resume_command(self, session_id: str) -> list[str]:
        # Gemini CLI 使用动态 index 恢复，无法精确指定 UUID
        return ["gemini", "--resume", "latest"]
