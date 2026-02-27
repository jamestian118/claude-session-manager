import argparse
import inspect
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import csm
from lib.models import SessionDetail, SessionSummary, ToolType
from lib.tui import TUI


def _session(session_id: str, tool_type: ToolType, ts: float) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        project=f"/tmp/{tool_type.name.lower()}-proj",
        first_display=f"first-{session_id}",
        last_display=f"last-{session_id}",
        timestamp_start=ts - 1000,
        timestamp_end=ts,
        message_count=3,
        tool_type=tool_type,
    )


def test_list_json_and_limit(monkeypatch, capsys) -> None:
    sessions = [
        _session("sid-3", ToolType.GEMINI, 3000),
        _session("sid-2", ToolType.CODEX, 2000),
        _session("sid-1", ToolType.CLAUDE, 1000),
    ]
    monkeypatch.setattr(csm.store, "load_sessions", lambda tool_filter=None: sessions)

    args = argparse.Namespace(tool=None, limit=2, json=True)
    rc = csm.cmd_list(args)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["session_id"] for row in payload] == ["sid-3", "sid-2"]
    assert payload[0]["tool"] == "gemini"


def test_list_invalid_limit_returns_2(capsys) -> None:
    args = argparse.Namespace(tool=None, limit=0, json=False)
    rc = csm.cmd_list(args)
    out = capsys.readouterr().out

    assert rc == 2
    assert "--limit" in out


def test_all_cmd_functions_annotate_int_return() -> None:
    cmd_funcs = [
        obj
        for name, obj in vars(csm).items()
        if name.startswith("cmd_") and callable(obj)
    ]
    assert cmd_funcs
    for fn in cmd_funcs:
        sig = inspect.signature(fn)
        assert sig.return_annotation in (int, "int")


def test_detail_exit_clears_detail_lines_cache() -> None:
    tui = TUI()
    tui.mode = "detail"
    tui.detail_scroll = 7
    tui.detail = SessionDetail(session_id="sid", project="/tmp", tool_type=ToolType.CLAUDE)
    tui._detail_lines = [("line-1", 0), ("line-2", 0)]

    tui._handle_detail_key(ord("q"), h=20)

    assert tui.mode == "list"
    assert tui._detail_lines == []
    assert tui.detail is None
    assert tui.detail_scroll == 0
