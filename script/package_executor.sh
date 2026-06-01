#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/projectpilot-executor"
TUI_DIR="$ROOT_DIR/tui/projectpilot-tui"

PYTHON_BIN="${PYTHON_BIN:-python3}"
CARGO_BIN="${CARGO_BIN:-$HOME/.cargo/bin/cargo}"

if [[ ! -x "$CARGO_BIN" ]]; then
  if command -v cargo >/dev/null 2>&1; then
    CARGO_BIN="$(command -v cargo)"
  else
    echo "cargo was not found. Install Rust first: https://rustup.rs" >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"

echo "==> Checking Python package"
"$PYTHON_BIN" -m compileall projectpilot >/dev/null

echo "==> Building Rust TUI"
"$CARGO_BIN" build --release --manifest-path "$TUI_DIR/Cargo.toml"

echo "==> Creating $DIST_DIR"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/bin" "$DIST_DIR/python" "$DIST_DIR/examples"

cp -R "$ROOT_DIR/projectpilot" "$DIST_DIR/python/projectpilot"
cp "$ROOT_DIR/pyproject.toml" "$DIST_DIR/pyproject.toml"
cp "$TUI_DIR/target/release/projectpilot-tui" "$DIST_DIR/bin/projectpilot-tui"

cat > "$DIST_DIR/bin/projectpilot-executor" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
APP_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$APP_HOME/python${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m projectpilot.executor "$@"
SH

cat > "$DIST_DIR/bin/projectpilot" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
APP_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$APP_HOME/python${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" -m projectpilot "$@"
SH

chmod +x "$DIST_DIR/bin/projectpilot-executor" "$DIST_DIR/bin/projectpilot" "$DIST_DIR/bin/projectpilot-tui"

cat > "$DIST_DIR/examples/remote-script-task.json" <<'JSON'
{
  "id": "task_script_1",
  "type": "run_remote_script",
  "approved": true,
  "ssh_host": "dev-server",
  "project_path": "/srv/app",
  "interpreter": "bash",
  "script": "set -euo pipefail\npwd\nhostname\n",
  "params": {
    "env": {
      "APP_ENV": "production"
    },
    "args": []
  }
}
JSON

cat > "$DIST_DIR/README_EXECUTOR.md" <<'MD'
# ProjectPilot Executor Bundle

This directory is a self-contained ProjectPilot Executor bundle.

## Commands

```bash
./bin/projectpilot-executor --version
./bin/projectpilot-executor setup
./bin/projectpilot-executor connect --once --json
./bin/projectpilot-executor ssh-hosts --json
./bin/projectpilot-tui --help
```

## Python Executor

The Python executor polls the backend, validates approved tasks, runs local or SSH work, and uploads results:

```bash
./bin/projectpilot-executor connect \
  --server-url http://127.0.0.1:8780 \
  --token dev-token \
  --executor-id eddz-executor \
  --allowed-root /Users/eddz/work \
  --once \
  --json
```

## Rust TUI Approval Client

The Rust TUI polls script tasks, displays the script, lets the user edit/reject/approve, then executes the script on the current server by default:

```bash
./bin/projectpilot-tui \
  --server-url http://127.0.0.1:8780 \
  --token dev-token \
  --executor-id eddz-tui \
  --execution-mode local \
  --once
```

Use `--execution-mode ssh` only for remote debugging from another machine.

## Remote Script Task Shape

See:

```text
examples/remote-script-task.json
```

The task must include an SSH host, absolute remote project path, script body, and `approved: true`.

## Notes

- Local execution runs on the same server where `projectpilot-tui` is launched.
- SSH debug mode uses the machine's normal `ssh`, `~/.ssh/config`, ssh-agent/keychain, and terminal password prompts when password auth is selected.
- The executor does not hold private keys for AI.
- Script execution uses SSH stdin, for example:

```text
ssh <host> "cd <project_path> && bash -s --" < script
```
MD

echo "==> Verifying bundle commands"
"$DIST_DIR/bin/projectpilot-executor" --version
"$DIST_DIR/bin/projectpilot-tui" --help

echo "==> Executor bundle ready: $DIST_DIR"
