#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
MCP_SERVER_NAME="${MCP_SERVER_NAME:-csm}"
STATE_DIR_DEFAULT="$HOME/Library/Application Support/claude-session-manager"
STATE_DIR="${CSM_STATE_DIR:-$STATE_DIR_DEFAULT}"

log() {
  printf '[uninstall] %s\n' "$*"
}

warn() {
  printf '[uninstall] WARN: %s\n' "$*" >&2
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
    exit 1
  fi
}

remove_claude() {
  if ! command -v claude >/dev/null 2>&1; then
    log "skip claude MCP removal (command not found)"
    return
  fi
  if claude mcp remove -s user "$MCP_SERVER_NAME"; then
    log "removed MCP from claude (scope=user)"
  else
    warn "unable to remove MCP from claude"
  fi
}

remove_codex() {
  if ! command -v codex >/dev/null 2>&1; then
    log "skip codex MCP removal (command not found)"
    return
  fi
  if codex mcp remove "$MCP_SERVER_NAME"; then
    log "removed MCP from codex"
  else
    warn "unable to remove MCP from codex"
  fi
}

remove_gemini() {
  if ! command -v gemini >/dev/null 2>&1; then
    log "skip gemini MCP removal (command not found)"
    return
  fi
  if gemini mcp remove -s user "$MCP_SERVER_NAME"; then
    log "removed MCP from gemini (scope=user)"
  else
    warn "unable to remove MCP from gemini"
  fi
}

cleanup_state() {
  if [[ -d "$STATE_DIR" ]]; then
    rm -rf "$STATE_DIR"
    log "removed state dir: $STATE_DIR"
  else
    log "state dir not found, skip: $STATE_DIR"
  fi
}

uninstall_python_package() {
  if "$PYTHON_BIN" -m pip show claude-session-manager >/dev/null 2>&1; then
    "$PYTHON_BIN" -m pip uninstall -y claude-session-manager
    log "uninstalled python package: claude-session-manager"
  else
    log "python package not installed, skip: claude-session-manager"
  fi
}

main() {
  ensure_python_and_pip

  log "removing MCP registrations"
  remove_claude
  remove_codex
  remove_gemini

  cleanup_state
  uninstall_python_package

  log "done"
}

main "$@"
