"""Integration helpers (macOS Terminal + cli-handoff-bundle snapshots).

Goals:
- Keep CSM usable while resuming a session in *another* terminal window/tab.
- Enable low-friction "handoff" between tools (Claude <-> Codex) via auto-generated
  handoff snapshots produced by `ai_handoff_watch.py`.
- Enable a "review-only" jump: open another tool with a strict reviewer prompt that
  forbids modifying files.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .models import SessionSummary, ToolType
from .utils import _tool_slug

logger = logging.getLogger(__name__)


def _resolve_exe(cmd0: str) -> str:
    """Resolve executable path for better reliability under AppleScript/Terminal environments."""
    return shutil.which(cmd0) or cmd0


def _shell_join(argv: list[str]) -> str:
    # Python 3.10+ is required by this project, but keep it simple anyway.
    return " ".join(shlex.quote(a) for a in argv)


def open_in_terminal(argv: list[str], cwd: str = "", terminal_app: str = "Terminal") -> tuple[bool, str]:
    """Open a new Terminal window/tab and run the given argv.

    macOS-only. On other platforms, prints a best-effort command string.
    """

    if not argv:
        return False, "Empty command"

    argv = [_resolve_exe(argv[0]), *argv[1:]]
    cmd = _shell_join(argv)
    if cwd and Path(cwd).exists():
        cmd = f"cd {shlex.quote(cwd)} && {cmd}"

    if sys.platform != "darwin":
        return False, f"(non-macOS) Run manually: {cmd}"

    # Pass the command as argv to avoid AppleScript string escaping pitfalls.
    applescript = (
        r"""
on run argv
  if (count of argv) is 0 then
    return
  end if
  set cmd to item 1 of argv
  tell application "%s"
    activate
    do script cmd
  end tell
end run
"""
        % terminal_app
    )

    try:
        p = subprocess.run(
            ["osascript", "-e", applescript, cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        return False, f"Failed to run osascript: {e}"

    out = (p.stdout or "").strip()
    if p.returncode != 0:
        return False, out or f"osascript failed with code {p.returncode}"
    return True, out or "OK"


def _handoff_tool_slug(tool_type: ToolType) -> str:
    return _tool_slug(tool_type)


def _default_handoff_roots() -> list[Path]:
    """Candidate global handoff roots (the parent that contains 'sessions/')."""

    roots: list[Path] = []

    env = os.environ.get("CSM_HANDOFF_ROOTS", "").strip()
    if env:
        for part in env.split(os.pathsep):
            part = part.strip()
            if not part:
                continue
            roots.append(Path(os.path.expanduser(part)))

    # New recommended location (LaunchAgent-safe on macOS).
    roots.append(Path.home() / "Library" / "Application Support" / "cli-handoff-bundle" / "_handoff")
    # Legacy/manual location.
    roots.append(Path.home() / "Documents" / "Code" / "cli-handoff-bundle" / "_handoff")

    # De-dup while preserving order.
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _handoff_snapshot_candidates(session: SessionSummary) -> list[Path]:
    """Return candidate snapshot paths for a session, most-preferred first."""

    tool = _handoff_tool_slug(session.tool_type)
    filename = f"{tool}-{session.session_id}.md"

    candidates: list[Path] = []

    # 1) Repo-local (if the project is inside a git repo). This is best for repo-first handoffs.
    project = session.project or ""
    if project and Path(project).exists():
        try:
            p = subprocess.run(
                ["git", "-C", project, "rev-parse", "--show-toplevel"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if p.returncode == 0:
                repo_root = (p.stdout or "").strip().splitlines()[0].strip()
                if repo_root:
                    candidates.append(Path(repo_root) / ".ai" / "handoff" / "sessions" / filename)
        except Exception as e:
            logger.debug(
                "failed to resolve repo-local handoff path: project=%s session_id=%s error=%s",
                project,
                session.session_id,
                e,
            )

    # 2) Global roots.
    for root in _default_handoff_roots():
        candidates.append(root / "sessions" / filename)

    return candidates


def _snapshot_score(path: Path) -> tuple[int, float]:
    """Heuristic to prefer richer snapshots when multiple roots exist.

    Some macOS launchd environments cannot access repo roots under ~/Documents due
    to privacy restrictions, so their global snapshots may lack repo context.
    When a richer snapshot exists (repo root + git status + .ai/handoff.md excerpt),
    prefer it even if it is slightly older.
    """

    score = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(8000)
        if "Repo root / 仓库根目录" in head:
            score += 3
        if "## Repo State / 仓库状态" in head:
            score += 3
        if "Repo Handoff File (excerpt)" in head:
            score += 2
    except Exception as e:
        logger.debug("failed to read snapshot head: path=%s error=%s", path, e)

    try:
        mtime = path.stat().st_mtime
    except Exception as e:
        logger.debug("failed to stat snapshot mtime: path=%s error=%s", path, e)
        mtime = 0.0

    return score, float(mtime)


def find_handoff_snapshot(session: SessionSummary) -> Path | None:
    existing: list[Path] = []
    for p in _handoff_snapshot_candidates(session):
        try:
            if p.exists():
                existing.append(p)
        except OSError:
            continue

    if not existing:
        return None
    if len(existing) == 1:
        return existing[0]

    return max(existing, key=_snapshot_score)


def _missing_snapshot_message(session: SessionSummary) -> str:
    tool = _handoff_tool_slug(session.tool_type)
    return (
        "找不到 handoff 快照文件。\n"
        "你可以先确保 ai_handoff_watch 在运行，或手动执行一次：\n"
        "  /usr/bin/python3 /Users/Zhuanz/Library/Application Support/cli-handoff-bundle/bin/ai_handoff_watch.py once\n"
        f"并检查是否生成了：{tool}-{session.session_id}.md"
    )


def build_takeover_prompt(snapshot_path: Path) -> str:
    # Keep it short: the snapshot itself contains more structure.
    return (
        "你现在接管一个进行中的任务。\n"
        f"请先阅读这个会话接力快照文件：{snapshot_path}\n"
        "它是自动生成的上下文压缩包（包含最近对话、关键工具输出、可能的 git 状态）。\n"
        "然后请输出：\n"
        "1) Goal/DoD（如果不清楚就先提 1-3 个问题）\n"
        "2) 当前阻塞点/失败证据（如有）\n"
        "3) 接下来 3-6 个按顺序的可执行步骤\n"
        "4) 你会跑哪些验证命令以及何时跑\n"
        "确认对齐后再开始修改代码。\n"
    )


def build_review_prompt(snapshot_path: Path, source_session: SessionSummary) -> str:
    csm = (Path(__file__).resolve().parent.parent / "csm.py")
    sid = source_session.session_id
    return (
        "你现在是 Reviewer（只做审查，不允许修改任何文件）。\n"
        f"请先阅读这个会话接力快照文件：{snapshot_path}\n"
        "如果仓库里存在 `.ai/handoff.md`，也请阅读它（里面应包含 Goal/DoD、验证命令、当前分支/commit、失败证据等）。\n"
        "\n"
        "审查规则：\n"
        "- 不要 apply_patch，不要改文件，不要提交。\n"
        "- 开头和结尾各跑一次：git status --porcelain（确认工作区保持 clean）。\n"
        "\n"
        "请输出（按顺序，尽量具体到文件/位置）：\n"
        "1) Change Summary\n"
        "2) Verification（你实际跑的命令；跑不了就写明原因并给可运行替代命令）\n"
        "3) Findings（BLOCKER/MAJOR/MINOR/NIT）\n"
        "4) Risk & Follow-ups\n"
        "\n"
        "完成审查后：\n"
        f"- 运行：python3 {csm} reviewed {sid}\n"
        "- 然后退出本工具（输入 exit/quit）。\n"
    )



def open_resume_in_terminal(session: SessionSummary) -> tuple[bool, str]:
    """Open the *same tool* resume command in another terminal."""

    if session.tool_type == ToolType.CLAUDE:
        cmd = ["claude", "--resume", session.session_id]
    elif session.tool_type == ToolType.CODEX:
        from .providers.codex import CodexProvider
        cmd = [CodexProvider._find_multitool_codex(), "resume", session.session_id]
    elif session.tool_type == ToolType.GEMINI:
        # Gemini CLI cannot resume by UUID reliably; provider uses latest.
        cmd = ["gemini", "--resume", "latest"]
    else:
        return False, f"Unsupported tool: {session.tool_type}"

    return open_in_terminal(cmd, cwd=session.project or "")


def _open_target_tool_with_prompt(
    *,
    target: ToolType,
    prompt: str,
    cwd: str,
) -> tuple[bool, str]:
    if target == ToolType.CODEX:
        cmd = ["codex", prompt]
    elif target == ToolType.CLAUDE:
        cmd = ["claude", prompt]
    elif target == ToolType.GEMINI:
        cmd = ["gemini", prompt]
    else:
        return False, f"Unsupported target: {target}"

    return open_in_terminal(cmd, cwd=cwd)


def build_mcp_takeover_prompt(session_id: str, tool_type_str: str) -> str:
    """构建 MCP 接力 prompt，让目标 CLI 通过 MCP 工具获取上下文。"""
    return (
        "你现在接管一个进行中的任务。\n"
        "请通过 MCP 工具 csm 的 get_session_context 获取上下文：\n"
        f"- session_id: {session_id}\n"
        f"- tool_type: {tool_type_str}\n"
        "拿到上下文后，输出：\n"
        "1) Goal/DoD\n"
        "2) 当前阻塞点\n"
        "3) 接下来 3-6 个步骤\n"
        "4) 验证命令\n"
        "确认对齐后再开始修改代码。\n"
    )


def open_mcp_handoff_in_terminal(session: SessionSummary, target: ToolType) -> tuple[bool, str]:
    """通过 MCP 接力方式在新终端打开目标工具。"""
    prompt = build_mcp_takeover_prompt(session.session_id, _handoff_tool_slug(session.tool_type))
    return _open_target_tool_with_prompt(target=target, prompt=prompt, cwd=session.project or "")


def open_handoff_in_terminal(session: SessionSummary, target: ToolType) -> tuple[bool, str]:
    """Open another tool in a new terminal and ask it to take over via a snapshot file."""

    snap = find_handoff_snapshot(session)
    if not snap:
        return False, _missing_snapshot_message(session)

    prompt = build_takeover_prompt(snap)
    return _open_target_tool_with_prompt(target=target, prompt=prompt, cwd=session.project or "")


def open_review_in_terminal(session: SessionSummary, target: ToolType) -> tuple[bool, str]:
    """Open another tool in a new terminal and ask it to do a review-only pass via a snapshot."""

    snap = find_handoff_snapshot(session)
    if not snap:
        return False, _missing_snapshot_message(session)

    prompt = build_review_prompt(snap, session)
    return _open_target_tool_with_prompt(target=target, prompt=prompt, cwd=session.project or "")
