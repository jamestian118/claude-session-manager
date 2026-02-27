from lib import store
from lib.models import SessionDetail, SessionSummary, ToolType


def _session(
    session_id: str,
    tool_type: ToolType,
    *,
    custom_name: str = "",
    first_display: str = "",
    last_display: str = "",
    project: str = "",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        project=project or "/tmp/project",
        first_display=first_display or "first",
        last_display=last_display or "last",
        timestamp_start=1000,
        timestamp_end=2000,
        message_count=1,
        tool_type=tool_type,
        custom_name=custom_name,
    )


def test_search_sessions_matches_multiple_fields_case_insensitive() -> None:
    sessions = [
        _session(
            "abc-001",
            ToolType.CLAUDE,
            custom_name="修复登录",
            first_display="需要排查登录失败",
            last_display="已定位",
            project="/Users/alice/workspace/app",
        ),
        _session(
            "xyz-002",
            ToolType.CODEX,
            custom_name="Refactor cache",
            first_display="optimize cache hit ratio",
            last_display="done",
            project="/Users/alice/workspace/api",
        ),
    ]

    by_custom_name = store.search_sessions(sessions, "登录")
    assert [s.session_id for s in by_custom_name] == ["abc-001"]

    by_project = store.search_sessions(sessions, "workspace/api")
    assert [s.session_id for s in by_project] == ["xyz-002"]

    by_tool = store.search_sessions(sessions, "codex")
    assert [s.session_id for s in by_tool] == ["xyz-002"]

    by_id = store.search_sessions(sessions, "ABC-001")
    assert [s.session_id for s in by_id] == ["abc-001"]


def test_load_sessions_grouping_and_resume_route(monkeypatch) -> None:
    class FakeProvider:
        tool_type = ToolType.CODEX

        def is_available(self):
            return True

        def load_sessions(self):
            return [
                _session("sid-old", ToolType.CODEX, first_display="older", last_display="older"),
                SessionSummary(
                    session_id="sid-new",
                    project="/tmp/new",
                    first_display="new",
                    last_display="new",
                    timestamp_start=2000,
                    timestamp_end=4000,
                    message_count=2,
                    tool_type=ToolType.CODEX,
                ),
            ]

        def get_resume_command(self, session_id):
            return ["codex", "resume", session_id]

    fake = FakeProvider()
    monkeypatch.setattr(store, "_PROVIDERS", [fake])

    # 覆盖 apply_custom_names/apply_flags 调用路径
    monkeypatch.setattr(store.session_names, "apply_custom_names", lambda sessions: None)
    monkeypatch.setattr(store.session_flags, "apply_flags", lambda sessions: None)

    sessions = store.load_sessions()
    assert [s.session_id for s in sessions] == ["sid-new", "sid-old"]

    grouped_project = store.group_by_project(sessions)
    assert set(grouped_project.keys()) == {"/tmp/new", "/tmp/project"}

    grouped_tool = store.group_by_tool(sessions)
    assert list(grouped_tool.keys()) == [ToolType.CODEX]
    assert len(grouped_tool[ToolType.CODEX]) == 2

    resume_cmd = store.get_resume_command(sessions[0])
    assert resume_cmd == ["codex", "resume", "sid-new"]


def test_store_detail_delete_and_custom_name_routes(monkeypatch) -> None:
    class FakeProvider:
        tool_type = ToolType.CLAUDE

        def is_available(self):
            return True

        def load_sessions(self):
            return []

        def load_session_detail(self, session_id, project=""):
            return SessionDetail(
                session_id=session_id,
                project=project,
                tool_type=ToolType.CLAUDE,
            )

        def delete_session(self, session_id):
            return {"jsonl": session_id == "sid-1"}

        def set_session_title(self, session_id, title):
            return True, "OK"

        def clear_session_title(self, session_id):
            return True, "OK"

        def load_stats(self):
            return {"ok": True}

    fake = FakeProvider()
    monkeypatch.setattr(store, "_PROVIDERS", [fake])

    monkeypatch.setattr(store.session_names, "apply_custom_name_to_detail", lambda detail: None)
    monkeypatch.setattr(store.session_flags, "apply_flags_to_detail", lambda detail: None)
    monkeypatch.setattr(store.session_names, "set_custom_name", lambda *args, **kwargs: (True, "OK"))
    monkeypatch.setattr(store.session_flags, "set_review_status", lambda *args, **kwargs: (True, "OK"))

    detail = store.load_session_detail("sid-1", ToolType.CLAUDE, project="/tmp/repo")
    assert detail is not None
    assert detail.session_id == "sid-1"

    result = store.delete_session("sid-1", ToolType.CLAUDE)
    assert result["jsonl"] is True
    assert result["custom_name"] is True
    assert result["review_status"] is True

    ok, msg = store.set_session_custom_name("sid-1", ToolType.CLAUDE, "new title")
    assert ok is True
    assert "tool title: OK" in msg

    ok_clear, msg_clear = store.set_session_custom_name("sid-1", ToolType.CLAUDE, "")
    assert ok_clear is True
    assert "tool title: OK" in msg_clear

    ok_status, _ = store.set_session_review_status("sid-1", ToolType.CLAUDE, "pending", anchor_ts_ms=1000)
    assert ok_status is True

    assert store.load_stats() == {"ok": True}
