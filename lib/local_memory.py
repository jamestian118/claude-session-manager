"""本地会话 memory 索引（SQLite），用于替代外部 Graphiti 依赖。"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .models import ToolType
from .utils import _default_state_dir, _tool_slug

logger = logging.getLogger(__name__)

_TOOL_MAP = {
    "claude": ToolType.CLAUDE,
    "codex": ToolType.CODEX,
    "gemini": ToolType.GEMINI,
}

_SCHEMA_READY_DBS: set[str] = set()


def db_path() -> Path:
    # 品控路径：state_dir/memory/session-memory.db
    return _default_state_dir() / "memory" / "session-memory.db"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_schema(conn, path)
    return conn


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _create_memory_entries_table(conn: sqlite3.Connection, table_name: str = "memory_entries") -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_quote_ident(table_name)} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            tool TEXT NOT NULL,
            title TEXT NOT NULL,
            project TEXT NOT NULL,
            cwd TEXT NOT NULL,
            git_branch TEXT NOT NULL,
            summary TEXT NOT NULL,
            files_changed_json TEXT NOT NULL,
            commands_run_json TEXT NOT NULL,
            errors_json TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            UNIQUE(session_id, tool)
        )
        """
    )


def _has_unique_session_tool(conn: sqlite3.Connection) -> bool:
    indexes = conn.execute("PRAGMA index_list('memory_entries')").fetchall()
    for idx in indexes:
        try:
            is_unique = bool(idx["unique"])
            idx_name = str(idx["name"])
        except Exception as e:
            logger.debug("failed to inspect sqlite index metadata: error=%s", e)
            continue
        if not is_unique:
            continue
        idx_name_escaped = idx_name.replace("'", "''")
        cols = conn.execute(f"PRAGMA index_info('{idx_name_escaped}')").fetchall()
        col_names = [str(c["name"]) for c in cols]
        if col_names == ["session_id", "tool"]:
            return True
    return False


def _migrate_memory_entries_schema(conn: sqlite3.Connection) -> None:
    # 旧库唯一键是 (session_id, tool, content_hash)；迁移到 (session_id, tool)，
    # 并按 updated_at/id 保留每组最新一条记录，避免历史重复条目继续增长。
    tmp_table = "memory_entries_new"
    backup_table = datetime.now(timezone.utc).strftime("memory_entries_backup_%Y%m%d%H%M%S%f")
    while _table_exists(conn, backup_table):
        backup_table += "_1"

    conn.execute(f"DROP TABLE IF EXISTS {_quote_ident(tmp_table)}")
    _create_memory_entries_table(conn, tmp_table)
    conn.execute(
        """
        INSERT INTO memory_entries_new (
            session_id, tool, title, project, cwd, git_branch,
            summary, files_changed_json, commands_run_json, errors_json,
            message_count, updated_at, content_hash
        )
        SELECT
            m.session_id, m.tool, m.title, m.project, m.cwd, m.git_branch,
            m.summary, m.files_changed_json, m.commands_run_json, m.errors_json,
            m.message_count, m.updated_at, m.content_hash
        FROM memory_entries AS m
        WHERE m.id = (
            SELECT m2.id
            FROM memory_entries AS m2
            WHERE m2.session_id = m.session_id AND m2.tool = m.tool
            ORDER BY m2.updated_at DESC, m2.id DESC
            LIMIT 1
        )
        """
    )
    conn.execute(f"ALTER TABLE {_quote_ident('memory_entries')} RENAME TO {_quote_ident(backup_table)}")
    conn.execute(f"ALTER TABLE {_quote_ident(tmp_table)} RENAME TO {_quote_ident('memory_entries')}")


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_entries_tool_updated ON memory_entries(tool, updated_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_entries_session_updated ON memory_entries(session_id, updated_at DESC)")


def _init_schema(conn: sqlite3.Connection, db_file: Path) -> None:
    db_key = str(db_file.resolve())
    if db_key in _SCHEMA_READY_DBS:
        return
    if not _table_exists(conn, "memory_entries"):
        _create_memory_entries_table(conn)
    elif not _has_unique_session_tool(conn):
        _migrate_memory_entries_schema(conn)
    _ensure_indexes(conn)
    conn.commit()
    _SCHEMA_READY_DBS.add(db_key)


def _build_summary(detail) -> str:
    parts = [f"工具: {detail.tool_type.label}", f"项目: {detail.project}"]
    if detail.cwd:
        parts.append(f"工作目录: {detail.cwd}")
    if detail.git_branch:
        parts.append(f"Git 分支: {detail.git_branch}")
    if detail.custom_name:
        parts.append(f"会话名称: {detail.custom_name}")

    for m in detail.messages[-12:]:
        parts.append(f"[{m.role}] {m.content[:500]}")
    if detail.files_changed:
        parts.append(f"修改文件: {', '.join(detail.files_changed[:30])}")
    if detail.commands_run:
        parts.append(f"执行命令: {', '.join(detail.commands_run[:20])}")
    if detail.errors:
        parts.append(f"错误: {', '.join(detail.errors[:10])}")
    return "\n".join(parts)


def _resolve_tool_type(tool_type_str: str) -> ToolType | None:
    return _TOOL_MAP.get((tool_type_str or "").strip().lower())


def sync_session(session_id: str, tool_type_str: str) -> dict:
    """同步单个会话到本地 memory 索引。"""
    tt = _resolve_tool_type(tool_type_str)
    if not tt:
        return {"error": f"未知工具类型: {tool_type_str}"}

    detail = store.load_session_detail(session_id, tt)
    if not detail:
        return {"error": f"找不到会话: {session_id}"}

    summary = _build_summary(detail)
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(summary.encode("utf-8", errors="replace")).hexdigest()
    title = detail.custom_name or f"{detail.tool_type.label} session {session_id[:8]}"
    tool = _tool_slug(detail.tool_type)

    try:
        with _connect() as conn:
            existed = (
                conn.execute(
                    """
                    SELECT 1
                    FROM memory_entries
                    WHERE session_id = ? AND tool = ?
                    LIMIT 1
                    """,
                    (detail.session_id, tool),
                ).fetchone()
                is not None
            )
            conn.execute(
                """
                INSERT INTO memory_entries (
                    session_id, tool, title, project, cwd, git_branch,
                    summary, files_changed_json, commands_run_json, errors_json,
                    message_count, updated_at, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, tool) DO UPDATE SET
                    title = excluded.title,
                    project = excluded.project,
                    cwd = excluded.cwd,
                    git_branch = excluded.git_branch,
                    summary = excluded.summary,
                    files_changed_json = excluded.files_changed_json,
                    commands_run_json = excluded.commands_run_json,
                    errors_json = excluded.errors_json,
                    message_count = excluded.message_count,
                    updated_at = excluded.updated_at,
                    content_hash = excluded.content_hash
                """,
                (
                    detail.session_id,
                    tool,
                    title,
                    detail.project or "",
                    detail.cwd or "",
                    detail.git_branch or "",
                    summary,
                    json.dumps(detail.files_changed or [], ensure_ascii=False),
                    json.dumps(detail.commands_run or [], ensure_ascii=False),
                    json.dumps(detail.errors or [], ensure_ascii=False),
                    len(detail.messages or []),
                    now,
                    content_hash,
                ),
            )
            inserted = not existed
        return {
            "ok": True,
            "session_id": detail.session_id,
            "tool": tool,
            "inserted": inserted,
            "content_hash": content_hash[:12],
        }
    except sqlite3.Error as e:
        return {"error": f"写入本地 memory 失败: {e}"}


def sync_all_recent(limit: int = 20) -> list[dict]:
    """批量同步最近会话。"""
    limit = max(1, int(limit or 20))
    sessions = store.load_sessions()[:limit]
    results: list[dict] = []
    for s in sessions:
        result = sync_session(s.session_id, _tool_slug(s.tool_type))
        results.append({"session_id": s.session_id, "tool": s.tool_type.label, "result": result})
    return results


def search_memory(query: str, limit: int = 10) -> list[dict]:
    """搜索本地 memory 索引。"""
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, int(limit or 10))
    token = q.lower()
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_id, tool, title, project, cwd, git_branch, summary,
                    files_changed_json, commands_run_json, errors_json,
                    message_count, updated_at
                FROM memory_entries
                WHERE
                    instr(lower(title), ?) > 0 OR
                    instr(lower(project), ?) > 0 OR
                    instr(lower(cwd), ?) > 0 OR
                    instr(lower(summary), ?) > 0 OR
                    instr(lower(files_changed_json), ?) > 0 OR
                    instr(lower(commands_run_json), ?) > 0 OR
                    instr(lower(errors_json), ?) > 0
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (token, token, token, token, token, token, token, limit),
            ).fetchall()
    except sqlite3.Error:
        return []

    out: list[dict] = []
    for r in rows:
        summary = str(r["summary"] or "")
        out.append(
            {
                "session_id": str(r["session_id"]),
                "tool": str(r["tool"]),
                "title": str(r["title"]),
                "project": str(r["project"]),
                "cwd": str(r["cwd"]),
                "git_branch": str(r["git_branch"]),
                "summary": summary[:600],
                "updated_at": str(r["updated_at"]),
                "message_count": int(r["message_count"] or 0),
                "files_changed": _safe_load_json_list(r["files_changed_json"]),
                "commands_run": _safe_load_json_list(r["commands_run_json"]),
                "errors": _safe_load_json_list(r["errors_json"]),
            }
        )
    return out


def _safe_load_json_list(raw: object) -> list[str]:
    try:
        parsed = json.loads(str(raw or "[]"))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(x) for x in parsed]


def get_status() -> dict:
    """返回本地 memory 存储状态。"""
    path = db_path()
    if not path.exists():
        return {
            "enabled": True,
            "db_path": str(path),
            "entries": 0,
            "sessions": 0,
            "latest_updated_at": "",
            "db_size_bytes": 0,
        }

    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS entries,
                    COUNT(DISTINCT tool || ':' || session_id) AS sessions,
                    COALESCE(MAX(updated_at), '') AS latest_updated_at
                FROM memory_entries
                """
            ).fetchone()
        return {
            "enabled": True,
            "db_path": str(path),
            "entries": int(row["entries"] or 0),
            "sessions": int(row["sessions"] or 0),
            "latest_updated_at": str(row["latest_updated_at"] or ""),
            "db_size_bytes": int(path.stat().st_size),
        }
    except sqlite3.Error as e:
        return {
            "enabled": True,
            "db_path": str(path),
            "error": f"读取本地 memory 状态失败: {e}",
        }
