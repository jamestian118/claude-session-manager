from lib import utils
from lib.models import SessionSummary, ToolType


def test_display_width_counts_cjk_as_double_width() -> None:
    assert utils.display_width("ab中文") == 6
    assert utils.display_width("A🙂中") == 5


def test_truncate_respects_cjk_width_and_appends_ellipsis() -> None:
    text = "ab中文cd"
    truncated = utils.truncate(text, 6)

    assert truncated.endswith("…")
    assert truncated == "ab中…"
    assert utils.display_width(truncated) <= 6


def test_ts_to_str_short_project_and_format_session_line(monkeypatch) -> None:
    fixed_home = "/Users/tester"
    monkeypatch.setattr(utils.Path, "home", lambda: utils.Path(fixed_home))

    readable = utils.ts_to_str(1700000000000, "%Y")
    assert readable.isdigit()

    assert utils.short_project("/Users/tester/work/a") == "~/work/a"
    assert utils.short_project("/opt/work/a") == "/opt/work/a"

    session = SessionSummary(
        session_id="sid-9",
        project="/Users/tester/work/a",
        first_display="first line",
        last_display="last line",
        timestamp_start=1700000000000,
        timestamp_end=1700000000000,
        message_count=2,
        tool_type=ToolType.CLAUDE,
        custom_name="阶段4",
        review_status="reviewed",
    )
    tag_meta, display = utils.format_session_line(session, short=True)
    assert "[Claude Code]R" in tag_meta
    assert "~/work/a" in tag_meta
    assert display.startswith("阶段4 | first line")


def test_tool_slug_maps_known_tools() -> None:
    assert utils._tool_slug(ToolType.CLAUDE) == "claude"
    assert utils._tool_slug(ToolType.CODEX) == "codex"
    assert utils._tool_slug(ToolType.GEMINI) == "gemini"


def test_default_state_dir_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("CSM_STATE_DIR", "~/tmp-csm-state")
    assert str(utils._default_state_dir()).endswith("tmp-csm-state")


def test_default_state_dir_uses_xdg_on_non_darwin(monkeypatch) -> None:
    monkeypatch.delenv("CSM_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")
    monkeypatch.setattr(utils.sys, "platform", "linux")
    assert str(utils._default_state_dir()) == "/tmp/xdg-state/claude-session-manager"
