#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="ProjectPilot"
APP_PROCESS_LOWER="projectpilot"
APP_ID="com.projectpilot.desktop"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/projectpilot-tauri-app"
APP_BUNDLE="$APP_DIR/src-tauri/target/release/bundle/macos/$APP_NAME.app"

kill_existing() {
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
  pkill -x "$APP_PROCESS_LOWER" >/dev/null 2>&1 || true
}

build_app() {
  cd "$APP_DIR"
  npm install
  npm run tauri:build
  codesign --force --deep --sign - "$APP_BUNDLE" >/dev/null
}

open_app() {
  if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "Built app bundle was not found: $APP_BUNDLE" >&2
    exit 1
  fi
  /usr/bin/open -n "$APP_BUNDLE"
}

verify_app() {
  sleep 2
  if pgrep -x "$APP_NAME" >/dev/null || pgrep -x "$APP_PROCESS_LOWER" >/dev/null; then
    return 0
  fi
  echo "$APP_NAME did not appear as a running process." >&2
  exit 1
}

kill_existing

case "$MODE" in
  run)
    build_app
    open_app
    ;;
  --dev|dev)
    cd "$APP_DIR"
    npm install
    npm run tauri:dev
    ;;
  --debug|debug)
    build_app
    lldb -- "$APP_BUNDLE/Contents/MacOS/$APP_PROCESS_LOWER"
    ;;
  --logs|logs)
    build_app
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\" OR process == \"$APP_PROCESS_LOWER\""
    ;;
  --telemetry|telemetry)
    build_app
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$APP_ID\""
    ;;
  --verify|verify)
    build_app
    open_app
    verify_app
    ;;
  *)
    echo "usage: $0 [run|--dev|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
