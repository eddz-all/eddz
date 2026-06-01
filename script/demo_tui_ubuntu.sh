#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/dist/projectpilot-executor/bin"
BACKEND="$BIN_DIR/projectpilot-executor"
TUI="$BIN_DIR/projectpilot-tui"

PORT="${PROJECTPILOT_TUI_DEMO_PORT:-8781}"
TOKEN="${PROJECTPILOT_TUI_DEMO_TOKEN:-dev-token}"
EXECUTOR_ID="${PROJECTPILOT_TUI_DEMO_EXECUTOR_ID:-eddz-mac}"
TMP_PARENT="${TMPDIR:-/tmp}"
TMP_DIR="$(mktemp -d "$TMP_PARENT/projectpilot-tui-ubuntu.XXXXXX")"
STORAGE="$TMP_DIR/storage.json"
LOG_FILE="$TMP_DIR/backend.log"

if [[ ! -x "$BACKEND" || ! -x "$TUI" ]]; then
  echo "Missing packaged executor binaries under: $BIN_DIR" >&2
  echo "Run: ./script/package_executor.sh" >&2
  exit 1
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

"$BACKEND" backend \
  --token "$TOKEN" \
  --storage "$STORAGE" \
  --port "$PORT" >"$LOG_FILE" 2>&1 &
BACKEND_PID="$!"

sleep 0.5

if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
  echo "Demo backend failed to start. Log:" >&2
  cat "$LOG_FILE" >&2
  exit 1
fi

"$BACKEND" enqueue \
  --storage "$STORAGE" \
  --payload-json '{"type":"run_remote_script","approved":true,"ssh_host":"ubuntu","project_path":"/home/hzy","interpreter":"bash","script":"set -euo pipefail\necho PROJECTPILOT_UBUNTU_OK\nwhoami\npwd\nuname -a\ndate\n","params":{"env":{"PROJECTPILOT_DEMO":"utm-ubuntu"},"args":[]}}' \
  --json >/dev/null

echo "Demo backend: http://127.0.0.1:$PORT"
echo "Target SSH host: ubuntu"
echo "Target remote path: /home/hzy"
echo "Storage: $STORAGE"
echo "Tip: this is a Mac-to-Ubuntu SSH debug demo. Press a if SSH key auth works, or p to enter the Ubuntu password."
echo

"$TUI" \
  --server-url "http://127.0.0.1:$PORT" \
  --token "$TOKEN" \
  --executor-id "$EXECUTOR_ID" \
  --execution-mode ssh \
  --once
