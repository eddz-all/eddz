# ProjectPilot

ProjectPilot is an intelligent Git assistant. It helps you understand repository state, plan safe next steps, run controlled Git operations, and review what ProjectPilot executed.

## Product Design

Read the GitHub-ready innovation design here: [ProjectPilot Innovation Design](docs/PROJECTPILOT_INNOVATION_DESIGN.md).

## Install

From this workspace:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
projectpilot --version
```

You can also run without installing:

```bash
python3 -m projectpilot --version
```

## Quick Start

```bash
projectpilot git quickstart .
projectpilot git doctor .
projectpilot git commit-plan .
```

`doctor` is the best daily entry point. It summarizes health, risk, findings, operation readiness, recent audit activity, and the next recommended Git step.

For Agent/backend integration, use the bundled smart Git analyzer:

```bash
projectpilot git map . --json
projectpilot git sync-plan . --json
projectpilot git analyze . --include map sync-plan commit-plan --json
```

`analyze` is read-only and returns a stable JSON envelope with `schema_version`, repository metadata, reports, operation plans, blocked operations, warnings, and next steps.

## Common Workflow

Review repository health:

```bash
projectpilot git doctor .
projectpilot git status .
projectpilot git suggest .
```

Review and prepare local changes:

```bash
projectpilot git commit-plan .
projectpilot git add .
projectpilot git add . --apply
projectpilot git commit .
projectpilot git commit . --apply
```

Work with branches and merge flow:

```bash
projectpilot git switch feature/demo . --create
projectpilot git switch feature/demo . --create --apply
projectpilot git merge feature/demo .
projectpilot git merge feature/demo . --apply
projectpilot git stash . --include-untracked
projectpilot git stash . --include-untracked --apply
```

Sync with upstream when configured:

```bash
projectpilot git fetch .
projectpilot git pull .
projectpilot git pull . --apply
projectpilot git push .
projectpilot git push . --apply
```

Review history:

```bash
projectpilot git log . -n 5
projectpilot git audit .
projectpilot git audit . --operation commit
```

Release or recovery-oriented operations:

```bash
projectpilot git tag v1.0.0 . -m "Release v1.0.0"
projectpilot git tag v1.0.0 . -m "Release v1.0.0" --apply
projectpilot git revert HEAD .
projectpilot git cherry-pick abc1234 .
projectpilot git danger-plan reset-hard .
```

Generate a report:

```bash
projectpilot git report .
```

## Safety Model

ProjectPilot is conservative by design:

- `status`, `explain`, `suggest`, `diff`, `log`, `report`, `commit-plan`, `add-plan`, `doctor`, and `audit` are read-only.
- `fetch` updates remote refs but does not modify working tree files.
- `add`, `commit`, `push`, `pull`, `switch`, `merge`, `stash`, `tag`, `revert`, and `cherry-pick` are dry-run unless `--apply` is present.
- `commit` only commits files that are already staged.
- `push` only runs a normal `git push` when the branch has an upstream, is ahead, and is not behind or diverged.
- `pull` only runs `git pull --ff-only` when the working tree is clean and the branch is behind but not ahead or diverged.
- `merge` only executes fast-forward merges in this phase.
- `revert` and `cherry-pick` default to `--no-commit`, so the result can be reviewed before committing.
- Force push, reset, clean, and rebase are exposed through blocked risk plans, not controlled execution.

Every `--apply` operation writes a JSONL audit entry to `.projectpilot/audit/git-operations.jsonl`. This local audit directory is ignored by Git.

## JSON Output

Several commands support `--json`, including:

```bash
projectpilot git status . --json
projectpilot git doctor . --json
projectpilot git audit . --json
projectpilot git commit-plan . --json
```

## Backend Integration

Member B integration functions are available without using the CLI:

```python
from projectpilot.integration.member_b import detect_local_environment, detect_local_git_status

git_status = detect_local_git_status("/path/to/project")
environment = detect_local_environment("/path/to/project")
```

Both functions return structured `dict` data. They do not write to the database or call backend APIs. The backend can store successful results as `GitStatus` and `EnvironmentSnapshot`, and can handle failures through the shared `success`, `error_type`, and `message` fields.

## Executor Connection Helper

Open the local Executor app:

```bash
projectpilot executor app
```

The Executor is also packaged as its own command, so it can be used like a standalone tool:

```bash
projectpilot-executor --version
projectpilot-executor setup
projectpilot-executor connect
projectpilot-executor ssh-hosts --json
```

Without installing the console script, run the same software module directly:

```bash
python3 -m projectpilot.executor --version
python3 -m projectpilot.executor connect --once --json
```

Open the native macOS window:

```bash
./script/build_and_run.sh
```

After the first build, the native bundle is available at:

```text
dist/ProjectPilot Executor Native.app
```

The native app opens a SwiftUI window for saving connection settings, choosing the allowed root folder, running one poll, and starting or stopping the executor loop. The browser app remains available through `projectpilot executor app` as a lightweight fallback.

For polling-mode integration, configure this machine once:

```bash
projectpilot executor setup \
  --server-url http://backend.example.test \
  --executor-id eddz-mac-local \
  --allowed-root /Users/eddz/work
```

The setup command prompts for the Executor token and stores the config in `~/.projectpilot/executor.json`.

Start the executor:

```bash
projectpilot executor connect
```

For backend development, process one task and exit:

```bash
projectpilot executor connect --once --json
```

Run a complete local Agent stack in one command. This starts an embedded backend, queues a smart Git task, runs the executor once, uploads the result, and prints the final backend state:

```bash
projectpilot executor run-local --project-path . --once --json
```

You can also pass an AI-generated backend task directly:

```bash
projectpilot executor run-local \
  --payload-json '{"type":"smart_git_analyze","project_path":".","analyses":["map","sync-plan"]}' \
  --once \
  --json
```

Run the minimal local Executor backend for MVP integration:

```bash
projectpilot executor backend \
  --token dev-token \
  --storage .projectpilot/executor-backend.json
```

Queue a detection task into that backend:

```bash
projectpilot executor enqueue \
  --storage .projectpilot/executor-backend.json \
  --type detect_environment \
  --project-path .
```

Then point the executor at the local backend:

```bash
projectpilot executor connect \
  --server-url http://127.0.0.1:8780 \
  --token dev-token \
  --executor-id eddz-mac-local \
  --allowed-root . \
  --once \
  --json
```

List SSH hosts visible to the executor:

```bash
projectpilot executor ssh-hosts --json
projectpilot executor ssh-hosts --resolve --json
```

The backend contract for the MVP is:

```text
POST /executor/poll
POST /executor/tasks/{task_id}/result
```

The executor supports read-only detection tasks and approved Git execution tasks:

```text
detect_git
detect_environment
smart_git_analyze
apply_git_operation
check_connection
detect_remote_git_status
detect_remote_environment
apply_remote_git_operation
run_remote_script
```

Local task paths must be inside `allowed-root`. `smart_git_analyze` is a read-only Agent task for scheme-A deployments where each machine runs its own ProjectPilot Agent and uploads smart Git JSON to the backend. Remote SSH tasks require `ssh_host` and, when they inspect or modify a project, an absolute remote `project_path`. Git and script execution tasks must include `approved: true`; optional `expected_command` lets the backend require the executor-generated Git command to match the approved plan exactly. Remote script tasks can include `script_sha256` so the executor verifies the approved script content before running it.

Local Git execution uses the same intelligent Git planner as the CLI. Remote Git execution never accepts raw shell commands; it maps structured `operation` and `params` fields to whitelisted Git commands, runs them through SSH, and returns before/after snapshots, stdout, stderr, and exit code.

Remote script execution is for backend-approved deployment or maintenance scripts. The executor sends the script over SSH stdin to `bash -s --` or `sh -s --`; it does not construct a shell command from free-form user text.

Example approved task:

```json
{
  "id": "task_42",
  "type": "apply_remote_git_operation",
  "approved": true,
  "ssh_host": "dev-server",
  "project_path": "/srv/app",
  "operation": "pull",
  "expected_command": ["git", "pull", "--ff-only"]
}
```

## Rust TUI Approval Client

The Rust TUI is a server-side approval and execution client for script tasks. The reviewer SSHs into the target server, starts the TUI there, reviews or edits the script, then approves local execution on that same server.

Build and run after installing Rust:

```bash
cd tui/projectpilot-tui
cargo run -- \
  --server-url http://127.0.0.1:8780 \
  --token dev-token \
  --executor-id eddz-tui \
  --execution-mode local \
  --once
```

Environment variables are also supported:

```bash
export PROJECTPILOT_SERVER_URL=http://127.0.0.1:8780
export PROJECTPILOT_EXECUTOR_TOKEN=dev-token
export PROJECTPILOT_EXECUTOR_ID=eddz-tui
cd tui/projectpilot-tui
cargo run -- --once
```

The TUI currently handles these backend task types:

```text
run_remote_script
apply_remote_script
execute_remote_script
run_script
apply_script
execute_script
```

For each task, it displays:

- task id and type;
- execution mode;
- SSH host, only when `--execution-mode ssh` is used;
- remote project path;
- interpreter;
- script SHA-256;
- full shell script with line numbers.

You can choose:

```text
a  approve and execute locally
e  edit script
r  reject and upload rejection result
q  quit without uploading a result
```

In the default local mode, the TUI executes scripts on the current server with:

```text
cd <project_path> && bash -s -- < script
```

SSH execution is still available for debugging from another machine:

```bash
projectpilot-tui ... --execution-mode ssh
```

In SSH mode, `a` uses key/agent auth and `p` allows terminal password auth.

If you edit the script, the uploaded result includes both the original script hash and final script hash.

To build a customer-facing Linux arm64 package that does not require Rust or Python on Ubuntu:

```bash
./script/package_agent_linux_arm64.sh
```

This creates:

```text
dist/projectpilot-agent-linux-arm64.tar.gz
```

## Fake Shell Backend

For local testing without the real backend, run:

```bash
./script/fake_shell_backend.py --port 8790 --token dev-token
```

Open:

```text
http://127.0.0.1:8790/
```

Then start the TUI against it:

```bash
./dist/projectpilot-executor/bin/projectpilot-tui \
  --server-url http://127.0.0.1:8790 \
  --token dev-token \
  --executor-id local-demo \
  --execution-mode local
```

The fake backend also accepts JSON shell tasks:

```bash
curl -X POST http://127.0.0.1:8790/send-shell \
  -H 'Content-Type: application/json' \
  --data '{"project_path":"/tmp","script":"echo hello\npwd\n"}'
```

## Executor Bundle

Package the whole executor as a runnable bundle:

```bash
./script/package_executor.sh
```

The output is:

```text
dist/projectpilot-executor/
  bin/projectpilot-executor
  bin/projectpilot
  bin/projectpilot-tui
  python/projectpilot/
  examples/remote-script-task.json
  README_EXECUTOR.md
```

Run it without installing the Python package:

```bash
dist/projectpilot-executor/bin/projectpilot-executor --version
dist/projectpilot-executor/bin/projectpilot-executor connect --once --json
dist/projectpilot-executor/bin/projectpilot-tui --help
```

Example approved remote script task:

```json
{
  "id": "task_script_1",
  "type": "run_remote_script",
  "approved": true,
  "ssh_host": "dev-server",
  "project_path": "/srv/app",
  "interpreter": "bash",
  "script": "set -euo pipefail\n./deploy.sh\n",
  "script_sha256": "expected_sha256_hex",
  "params": {
    "env": {
      "APP_ENV": "production"
    },
    "args": []
  }
}
```
