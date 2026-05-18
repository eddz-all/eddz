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

Generate a report:

```bash
projectpilot git report .
```

## Safety Model

ProjectPilot is conservative by design:

- `status`, `explain`, `suggest`, `diff`, `log`, `report`, `commit-plan`, `add-plan`, `doctor`, and `audit` are read-only.
- `fetch` updates remote refs but does not modify working tree files.
- `add`, `commit`, `push`, and `pull` are dry-run unless `--apply` is present.
- `commit` only commits files that are already staged.
- `push` only runs a normal `git push` when the branch has an upstream, is ahead, and is not behind or diverged.
- `pull` only runs `git pull --ff-only` when the working tree is clean and the branch is behind but not ahead or diverged.
- Force push, reset, clean, and rebase are not supported by controlled execution.

Every `--apply` operation writes a JSONL audit entry to `.projectpilot/audit/git-operations.jsonl`. This local audit directory is ignored by Git.

## JSON Output

Several commands support `--json`, including:

```bash
projectpilot git status . --json
projectpilot git doctor . --json
projectpilot git audit . --json
projectpilot git commit-plan . --json
```
