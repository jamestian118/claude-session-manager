#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MCP_SERVER_NAME="${MCP_SERVER_NAME:-csm}"

log() {
  printf '[install] %s\n' "$*"
}

warn() {
  printf '[install] WARN: %s\n' "$*" >&2
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    warn "missing command: $cmd"
    return 1
  fi
  return 0
}

ensure_python_and_pip() {
  require_command "$PYTHON_BIN" || {
    warn "set PYTHON_BIN to a valid Python 3 executable."
    exit 1
  }
  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    warn "pip is unavailable for $PYTHON_BIN"
    warn "try: $PYTHON_BIN -m ensurepip --upgrade"
    exit 1
  fi
}

register_claude() {
  if ! command -v claude >/dev/null 2>&1; then
    log "skip claude MCP registration (command not found)"
    return
  fi
  claude mcp remove -s user "$MCP_SERVER_NAME" >/dev/null 2>&1 || true
  if claude mcp add -s user "$MCP_SERVER_NAME" -- "$PYTHON_BIN" "$ROOT_DIR/csm.py" mcp; then
    log "registered MCP for claude (scope=user)"
  else
    warn "failed to register MCP for claude"
  fi
}

register_codex() {
  if ! command -v codex >/dev/null 2>&1; then
    log "skip codex MCP registration (command not found)"
    return
  fi
  codex mcp remove "$MCP_SERVER_NAME" >/dev/null 2>&1 || true
  if codex mcp add "$MCP_SERVER_NAME" -- "$PYTHON_BIN" "$ROOT_DIR/csm.py" mcp; then
    log "registered MCP for codex"
  else
    warn "failed to register MCP for codex"
  fi
}

register_gemini() {
  if ! command -v gemini >/dev/null 2>&1; then
    log "skip gemini MCP registration (command not found)"
    return
  fi
  gemini mcp remove -s user "$MCP_SERVER_NAME" >/dev/null 2>&1 || true
  if gemini mcp add -s user "$MCP_SERVER_NAME" "$PYTHON_BIN" "$ROOT_DIR/csm.py" mcp; then
    log "registered MCP for gemini (scope=user)"
  else
    warn "failed to register MCP for gemini"
  fi
}

main() {
  ensure_python_and_pip

  log "installing python package (editable)"
  "$PYTHON_BIN" -m pip install -e "$ROOT_DIR"

  log "registering MCP servers"
  register_claude
  register_codex
  register_gemini

  log "done"
}

main "$@"
