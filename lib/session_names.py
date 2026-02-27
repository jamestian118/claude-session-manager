"""Session naming (user-defined) for CSM.

CSM aggregates sessions from multiple tools (Claude/Codex/Gemini). Those tools do not share a
compatible "rename" API, and in some cases do not expose any stable session title field.

So we implement a tool-agnostic layer: a persistent mapping from (tool, session_id) -> custom name.
This affects CSM listing/search/detail UI only, and keeps resume/handoff semantics unchanged.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import logging
import os
import sys
import time
from pathlib import Path

from .models import ToolType, SessionDetail, SessionSummary

logger = logging.getLogger(__name__)


def _tool_slug(tool_type: ToolType) -> str:
    if tool_type == ToolType.CLAUDE:
        return "claude"
    if tool_type == ToolType.CODEX:
        return "codex"
    if tool_type == ToolType.GEMINI:
        return "gemini"
    return tool_type.label.lower()


def _default_state_dir() -> Path:
    # Allow explicit override (useful for debugging / portable setups).
    env = os.environ.get("CSM_STATE_DIR", "").strip()
    if env:
        return Path(os.path.expanduser(env))

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "claude-session-manager"

    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(os.path.expanduser(xdg)) / "claude-session-manager"

    return Path.home() / ".local" / "state" / "claude-session-manager"


def _names_file() -> Path:
    return _default_state_dir() / "session-names.json"


@contextmanager
def _locked_names_file():
    path = _names_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "a", encoding="utf-8", errors="replace") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _key(tool_type: ToolType, session_id: str) -> str:
    return f"{_tool_slug(tool_type)}:{session_id}"


def _safe_load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        # Preserve the corrupted file for debugging.
        try:
            backup = path.with_name(path.name + f".corrupt-{int(time.time())}")
            path.rename(backup)
        except OSError:
            pass
        return {}
    except OSError:
        return {}


def load_names() -> dict[str, str]:
    """Load custom names mapping."""
    raw = _safe_load_json(_names_file())
    names = raw.get("names") if isinstance(raw, dict) else None
    if not isinstance(names, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in names.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        vv = " ".join(v.split()).strip()
        if not vv:
            continue
        out[k] = vv
    return out


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def set_custom_name(tool_type: ToolType, session_id: str, name: str) -> tuple[bool, str]:
    """Set (or clear) a custom name for a session.

    Returns (ok, message).
    """
    session_id = (session_id or "").strip()
    if not session_id:
        return False, "Empty session_id"

    cleaned = " ".join((name or "").split()).strip()
    k = _key(tool_type, session_id)

    try:
        with _locked_names_file():
            names = load_names()
            if cleaned:
                names[k] = cleaned
            else:
                names.pop(k, None)

            payload = {
                "version": 1,
                "updated_at": int(time.time()),
                "names": names,
            }
            _atomic_write_json(_names_file(), payload)
    except OSError as e:
        return False, f"Failed to write names file: {e}"

    if cleaned:
        return True, f"OK: {cleaned}"
    return True, "OK: cleared"


def apply_custom_names(sessions: list[SessionSummary]) -> None:
    """Mutate SessionSummary objects in-place to attach custom_name."""
    if not sessions:
        return
    names = load_names()
    for s in sessions:
        try:
            s.custom_name = names.get(_key(s.tool_type, s.session_id), "")
        except Exception as e:
            logger.debug(
                "failed to apply custom name: tool=%s session_id=%s error=%s",
                s.tool_type.label,
                s.session_id,
                e,
            )
            continue


def apply_custom_name_to_detail(detail: SessionDetail) -> None:
    names = load_names()
    detail.custom_name = names.get(_key(detail.tool_type, detail.session_id), "")
