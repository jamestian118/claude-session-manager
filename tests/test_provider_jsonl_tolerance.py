import json

from lib.providers.claude import ClaudeProvider
from lib.providers.codex import CodexProvider


def test_codex_provider_tolerates_corrupted_history_jsonl(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    history_file = tmp_path / ".codex" / "history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        "\n".join(
            [
                "{bad json line",
                json.dumps({"session_id": "sid-1", "ts": 10, "text": "first"}),
                json.dumps({"session_id": "sid-1", "ts": 20, "text": "second"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    provider = CodexProvider()
    sessions = provider.load_sessions()

    assert len(sessions) == 1
    assert sessions[0].session_id == "sid-1"
    assert sessions[0].first_display == "first"
    assert sessions[0].last_display == "second"
    assert sessions[0].message_count == 2


def test_claude_provider_tolerates_corrupted_project_jsonl(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    project_dir = tmp_path / ".claude" / "projects" / "-tmp-proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    session_file = project_dir / "sid-2.jsonl"
    session_file.write_text(
        "\n".join(
            [
                "{broken line",
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-02-27T12:00:00Z",
                        "cwd": "/tmp/proj",
                        "message": {"content": "修复连接错误"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-02-27T12:00:10Z",
                        "message": {"content": "done"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    provider = ClaudeProvider()
    sessions = provider.load_sessions()

    assert len(sessions) == 1
    assert sessions[0].session_id == "sid-2"
    assert sessions[0].project == "/tmp/proj"
    assert sessions[0].first_display == "修复连接错误"
