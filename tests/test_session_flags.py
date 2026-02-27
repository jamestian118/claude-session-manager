from lib import session_flags
from lib.models import SessionSummary, ToolType


def _summary(ts_end_ms: int) -> SessionSummary:
    return SessionSummary(
        session_id="sess-1",
        project="/tmp/project",
        first_display="first",
        last_display="last",
        timestamp_start=1000,
        timestamp_end=ts_end_ms,
        message_count=2,
        tool_type=ToolType.CLAUDE,
    )


def test_apply_flags_auto_resets_rechecked_when_new_messages(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CSM_STATE_DIR", str(tmp_path))

    ok, msg = session_flags.set_review_status(
        ToolType.CLAUDE,
        "sess-1",
        "rechecked",
        anchor_ts_ms=1000,
    )
    assert ok, msg

    sessions = [_summary(ts_end_ms=2000)]
    session_flags.apply_flags(sessions)

    assert sessions[0].review_status == ""
    assert sessions[0].review_updated_at == 0
    assert session_flags.load_flags() == {}


def test_apply_flags_keeps_rechecked_when_no_new_messages(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CSM_STATE_DIR", str(tmp_path))

    ok, msg = session_flags.set_review_status(
        ToolType.CLAUDE,
        "sess-1",
        "rechecked",
        anchor_ts_ms=2000,
    )
    assert ok, msg

    sessions = [_summary(ts_end_ms=2000)]
    session_flags.apply_flags(sessions)

    assert sessions[0].review_status == "rechecked"
    assert sessions[0].review_updated_at > 0
    assert "claude:sess-1" in session_flags.load_flags()
