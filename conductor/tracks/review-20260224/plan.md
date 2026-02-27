# Review Plan: claude-session-manager

## 1. 发现的错误点 (Bug & Error Handling)
- **Critical Data Loss / Non-Atomic Writes**: 在 `lib/providers/claude.py` 和 `lib/providers/codex.py` 中，`delete_session` 方法通过直接以 `"w"` 模式打开 `history.jsonl` 和全局状态文件来重写它们。如果应用程序被中断或崩溃，整个文件将被截断并永久丢失。
  - **修复建议**: 使用临时文件和 `os.replace` 实现原子写入。
- **Database Duplication Leak**: 在 `lib/local_memory.py` 中，SQLite 架构使用了 `UNIQUE(session_id, tool, content_hash)`。因为每次会话获取新消息时哈希值都会改变，`sync_session` 会插入一个全新的重复行，而不是更新旧行。
  - **修复建议**: 架构应该强制执行 `UNIQUE(session_id, tool)` 并使用 `INSERT OR REPLACE`。
- **Race Conditions in State Files**: `lib/session_flags.py` 和 `lib/session_names.py` 在没有文件锁定的情况下对 JSON 文件执行“读取-修改-写入”循环。如果两个 `csm` 实例并发执行，它们会互相覆盖。
  - **修复建议**: 使用 `fcntl.flock` 包装读/写操作。
- **Unhandled Encoding Edge Cases**: 文件读取操作（如 `open(..., encoding="utf-8")`）缺少 `errors="replace"`。单个日志文件中的无效字节将引发 `UnicodeDecodeError`，从而破坏整个工具列表。

## 2. 可优化点 (Optimization & Architecture)
- **Performance Bottleneck (O(N) Startup)**: Provider 的 `load_sessions` 方法在每次调用时都会同步扫描和解析目录中的所有 JSONL 文件。对于重度用户，这会导致严重的 TUI 延迟。
  - **优化建议**: 实现一个缓存层，将文件的 `st_mtime` 映射到解析后的元数据。
