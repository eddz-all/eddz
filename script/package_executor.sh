#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/projectpilot-executor"

PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"

echo "==> Checking Python package"
"$PYTHON_BIN" -m compileall projectpilot >/dev/null

echo "==> Creating $DIST_DIR"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR/bin" "$DIST_DIR/python" "$DIST_DIR/examples"

cp -R "$ROOT_DIR/projectpilot" "$DIST_DIR/python/projectpilot"
cp "$ROOT_DIR/pyproject.toml" "$DIST_DIR/pyproject.toml"

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

chmod +x "$DIST_DIR/bin/projectpilot-executor" "$DIST_DIR/bin/projectpilot"

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
./bin/projectpilot-executor publish --print-only --json
./bin/projectpilot-executor ssh-hosts --json
```

On the server-b Ubuntu VM, `./bin/projectpilot` starts the built-in executor profile directly:

```bash
./bin/projectpilot
```

Built-in profile:

```text
server_url: https://printable-played-chances-response.trycloudflare.com
executor_id: server-b
allowed_root: /home/hzy
project_path: /home/hzy/project/web
token: dev-token
interval: 3
mode: central
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

## Task Publisher

Queue a smart Git task against a compatible backend task endpoint:

```bash
./bin/projectpilot-executor publish \
  --server-url http://127.0.0.1:8780 \
  --token dev-token \
  --executor-id server-b \
  --project-path /home/hzy/project/web \
  --type smart_git_analyze \
  --analyses map sync-plan commit-plan \
  --json
```

Trigger a project/server detection flow on the backend:

```bash
./bin/projectpilot-executor publish \
  --server-url http://127.0.0.1:8780 \
  --token dev-token \
  --mode project-detect \
  --project-id 1 \
  --server-id 1 \
  --json
```

## Remote Script Task Shape

See:

```text
examples/remote-script-task.json
```

The task must include an SSH host, absolute remote project path, script body, and `approved: true`.

## Notes

- Local execution runs on the same server where `projectpilot-executor` is launched.
- SSH execution uses the machine's normal `ssh`, `~/.ssh/config`, ssh-agent/keychain, and terminal password prompts when password auth is selected.
- The executor does not hold private keys for AI.
- Script execution uses SSH stdin, for example:

```text
ssh <host> "cd <project_path> && bash -s --" < script
```
MD

echo "==> Verifying bundle commands"
"$DIST_DIR/bin/projectpilot-executor" --version

echo "==> Executor bundle ready: $DIST_DIR"
