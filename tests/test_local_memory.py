from lib import local_memory
from lib.models import ChatMessage, SessionDetail, ToolType


def _detail(*, summary_hint: str, cwd: str = "/tmp/proj", branch: str = "main") -> SessionDetail:
    return SessionDetail(
        session_id="sid-123",
        project="/tmp/proj",
        tool_type=ToolType.CODEX,
        cwd=cwd,
        git_branch=branch,
        custom_name="Memory CRUD",
        messages=[
            ChatMessage(role="user", content=f"用户问题: {summary_hint}"),
            ChatMessage(role="assistant", content="已处理"),
        ],
        files_changed=["lib/a.py", "lib/b.py"],
        commands_run=["pytest -q"],
        errors=["none"],
    )


def test_local_memory_sync_search_update_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CSM_STATE_DIR", str(tmp_path))

    first = _detail(summary_hint="alpha")
    second = _detail(summary_hint="beta", branch="feature/phase4")

    state = {"detail": first}

    def fake_load_session_detail(session_id, tool_type):
        assert session_id == "sid-123"
        assert tool_type == ToolType.CODEX
        return state["detail"]

    monkeypatch.setattr(local_memory.store, "load_session_detail", fake_load_session_detail)

    create_result = local_memory.sync_session("sid-123", "codex")
    assert create_result["ok"] is True
    assert create_result["inserted"] is True
    assert create_result["tool"] == "codex"

    found_first = local_memory.search_memory("alpha", limit=5)
    assert len(found_first) == 1
    assert found_first[0]["session_id"] == "sid-123"
    assert found_first[0]["git_branch"] == "main"

    state["detail"] = second
    update_result = local_memory.sync_session("sid-123", "codex")
    assert update_result["ok"] is True
    assert update_result["inserted"] is False

    found_second = local_memory.search_memory("beta", limit=5)
    assert len(found_second) == 1
    assert found_second[0]["git_branch"] == "feature/phase4"
    assert found_second[0]["files_changed"] == ["lib/a.py", "lib/b.py"]

    status = local_memory.get_status()
    assert status["entries"] == 1
    assert status["sessions"] == 1
    assert status["db_size_bytes"] > 0


def test_local_memory_sync_session_rejects_unknown_tool(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CSM_STATE_DIR", str(tmp_path))
    result = local_memory.sync_session("sid-123", "unknown")
    assert "error" in result
