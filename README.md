# ProjectPilot

ProjectPilot is an intelligent Git assistant. It helps you understand repository state, plan safe next steps, run controlled Git operations, and review what ProjectPilot executed.

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

Open the native macOS window:

```bash
./script/build_and_run.sh
```

After the first build, the native bundle is available at:

```text
dist/ProjectPilot Executor Native.app
```

The native app opens a SwiftUI window for saving connection settings, choosing the allowed root folder, running one poll, and starting or stopping the read-only executor loop. The browser app remains available through `projectpilot executor app` as a lightweight fallback.

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

The executor only supports approved read-only task types in this phase:

```text
detect_git
detect_environment
check_connection
detect_remote_git_status
detect_remote_environment
```

Local task paths must be inside `allowed-root`. Remote SSH tasks require `ssh_host` and, when they inspect a project, an absolute remote `project_path`. The executor builds the SSH command from a whitelist template and posts stdout, stderr, and exit code back to the backend.
