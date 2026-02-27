"""Session flags / metadata stored by CSM.

This is intentionally tool-agnostic: we store a persistent mapping from
  (tool, session_id) -> flags
so the user can track status across Claude/Codex/Gemini sessions.

Currently supported:
- review_status: "", "pending", "reviewed", "rechecked"
  - pending: review requested / in progress
  - reviewed: review finished, waiting for implementer fixes/recheck
  - rechecked: implementer fixed + re-verified (finalized)

Auto-reset rule:
- If a session is marked as "rechecked" and the underlying session receives new messages
  (timestamp_end increases), it automatically resets back to unreviewed.

The storage file is separate from `session-names.json` to avoid breaking older installs.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import sys
import time
from pathlib import Path

from .models import SessionDetail, SessionSummary, ToolType

_REVIEW_STATUSES = {"", "pending", "reviewed", "rechecked"}


def _tool_slug(tool_type: ToolType) -> str:
    if tool_type == ToolType.CLAUDE:
        return "claude"
    if tool_type == ToolType.CODEX:
        return "codex"
    if tool_type == ToolType.GEMINI:
        return "gemini"
    return tool_type.label.lower()


def _default_state_dir() -> Path:
    env = os.environ.get("CSM_STATE_DIR", "").strip()
    if env:
        return Path(os.path.expanduser(env))

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "claude-session-manager"

    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(os.path.expanduser(xdg)) / "claude-session-manager"

    return Path.home() / ".local" / "state" / "claude-session-manager"


def _flags_file() -> Path:
    return _default_state_dir() / "session-flags.json"


@contextmanager
def _locked_flags_file():
    path = _flags_file()
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
        # Preserve the corrupted file for debugging and start fresh.
        try:
            backup = path.with_name(path.name + f".corrupt-{int(time.time())}")
            path.rename(backup)
        except OSError:
            pass
        return {}
    except OSError:
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _normalize_review_status(raw: object) -> str:
    s = str(raw or "").strip().lower()
    # Backward-compat: older versions used "done".
    if s == "done":
        return "reviewed"
    if s in _REVIEW_STATUSES:
        return s
    return ""


def _load_payload() -> dict:
    raw = _safe_load_json(_flags_file())
    if not isinstance(raw, dict):
        return {"version": 1, "updated_at": 0, "flags": {}}
    flags = raw.get("flags")
    if not isinstance(flags, dict):
        flags = {}
    return {
        "version": int(raw.get("version", 1) or 1),
        "updated_at": int(raw.get("updated_at", 0) or 0),
        "flags": flags,
    }


def _save_payload(flags: dict[str, dict]) -> None:
    payload = {
        "version": 1,
        "updated_at": int(time.time()),
        "flags": flags,
    }
    _atomic_write_json(_flags_file(), payload)


def load_flags() -> dict[str, dict]:
    """Load session flags mapping.

    Returns a mapping: key -> normalized record dict.
    """

    payload = _load_payload()
    raw_flags = payload.get("flags", {})
    if not isinstance(raw_flags, dict):
        return {}

    out: dict[str, dict] = {}
    for k, v in raw_flags.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue

        rs = _normalize_review_status(v.get("review_status", ""))
        updated_at = v.get("review_updated_at", 0)
        if not isinstance(updated_at, int):
            updated_at = 0

        anchor_ts_ms = v.get("review_anchor_ts_ms", 0)
        if isinstance(anchor_ts_ms, float):
            anchor_ts_ms = int(anchor_ts_ms)
        if not isinstance(anchor_ts_ms, int):
            anchor_ts_ms = 0

        if not rs:
            continue

        out[k] = {
            "review_status": rs,
            "review_updated_at": updated_at,
            "review_anchor_ts_ms": anchor_ts_ms,
        }

    return out


def set_review_status(
    tool_type: ToolType,
    session_id: str,
    status: str,
    *,
    anchor_ts_ms: int | None = None,
) -> tuple[bool, str]:
    """Set review status for a session.

    status: "" | "pending" | "reviewed" | "rechecked"
    anchor_ts_ms: optional session timestamp_end (ms) at the moment of marking.
    Returns (ok, message).
    """

    session_id = (session_id or "").strip()
    if not session_id:
        return False, "Empty session_id"

    status = _normalize_review_status(status)

    if status not in _REVIEW_STATUSES:
        return False, f"Invalid review status: {status}"

    k = _key(tool_type, session_id)

    try:
        with _locked_flags_file():
            payload = _load_payload()
            flags = payload.get("flags", {})
            if not isinstance(flags, dict):
                flags = {}

            if status:
                rec = {
                    "review_status": status,
                    "review_updated_at": int(time.time()),
                }
                if anchor_ts_ms is not None:
                    try:
                        rec["review_anchor_ts_ms"] = int(anchor_ts_ms)
                    except Exception:
                        pass
                flags[k] = rec
            else:
                flags.pop(k, None)

            _save_payload(flags)
    except OSError as e:
        return False, f"Failed to write flags file: {e}"

    if status:
        return True, f"OK: {status}"
    return True, "OK: cleared"


def _maybe_reset_rechecked(
    *,
    status: str,
    anchor_ts_ms: int,
    session_ts_ms: int,
) -> bool:
    if status != "rechecked":
        return False
    if anchor_ts_ms <= 0 or session_ts_ms <= 0:
        return False
    return session_ts_ms > anchor_ts_ms


def apply_flags(sessions: list[SessionSummary]) -> None:
    """Mutate SessionSummary objects in-place to attach review fields.

    Also auto-resets "rechecked" sessions when new messages are detected.
    """

    if not sessions:
        return

    try:
        with _locked_flags_file():
            payload = _load_payload()
            flags = payload.get("flags", {})
            if not isinstance(flags, dict):
                flags = {}

            changed = False

            for s in sessions:
                try:
                    k = _key(s.tool_type, s.session_id)
                    rec = flags.get(k, {}) if isinstance(flags.get(k), dict) else {}

                    status = _normalize_review_status(rec.get("review_status", ""))
                    updated_at = rec.get("review_updated_at", 0)
                    if not isinstance(updated_at, int):
                        updated_at = 0

                    anchor_ts_ms = rec.get("review_anchor_ts_ms", 0)
                    if isinstance(anchor_ts_ms, float):
                        anchor_ts_ms = int(anchor_ts_ms)
                    if not isinstance(anchor_ts_ms, int):
                        anchor_ts_ms = 0

                    session_ts_ms = int(s.timestamp_end or 0)

                    # Backward compat: upgrade persisted "done" -> "reviewed".
                    if str(rec.get("review_status", "")).strip().lower() == "done":
                        rec["review_status"] = "reviewed"
                        flags[k] = rec
                        changed = True
                        status = "reviewed"

                    if _maybe_reset_rechecked(status=status, anchor_ts_ms=anchor_ts_ms, session_ts_ms=session_ts_ms):
                        flags.pop(k, None)
                        changed = True
                        status = ""
                        updated_at = 0

                    s.review_status = status
                    s.review_updated_at = int(updated_at or 0)
                except Exception:
                    continue

            if changed:
                try:
                    _save_payload(flags)
                except OSError:
                    # If we cannot persist, still keep the in-memory view consistent.
                    pass
    except OSError:
        return


def apply_flags_to_detail(detail: SessionDetail) -> None:
    flags = load_flags()
    rec = flags.get(_key(detail.tool_type, detail.session_id), {})
    detail.review_status = str(rec.get("review_status", "") or "")
    detail.review_updated_at = int(rec.get("review_updated_at", 0) or 0)
