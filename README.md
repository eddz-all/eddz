# ProjectPilot

ProjectPilot is starting as an intelligent Git assistant.

The first MVP focuses on local Git repositories:

- collect structured Git status;
- explain the current repository state;
- suggest safe next steps;
- generate Markdown Git status reports;
- avoid executing high-risk Git operations.

## Usage

Run from this workspace with:

```bash
python3 -m projectpilot git status /path/to/repo
python3 -m projectpilot git explain /path/to/repo
python3 -m projectpilot git suggest /path/to/repo
python3 -m projectpilot git report /path/to/repo
python3 -m projectpilot git diff /path/to/repo --stat
python3 -m projectpilot git log /path/to/repo -n 5
python3 -m projectpilot git fetch /path/to/repo
python3 -m projectpilot git commit-plan /path/to/repo
python3 -m projectpilot git add-plan /path/to/repo
python3 -m projectpilot git add /path/to/repo
python3 -m projectpilot git add /path/to/repo --apply
python3 -m projectpilot git commit /path/to/repo
python3 -m projectpilot git commit /path/to/repo --apply
python3 -m projectpilot git push /path/to/repo
python3 -m projectpilot git push /path/to/repo --apply
python3 -m projectpilot git pull /path/to/repo
python3 -m projectpilot git pull /path/to/repo --apply
```

After installation, the same commands are available through:

```bash
projectpilot git status
```

## Current Scope

This version is conservative by design. It can run `fetch`, which updates remote refs but does not modify working tree files. It does not run `pull`, `push`, `commit`, `reset`, `clean`, or other higher-risk Git operations.

`commit-plan` is still read-only. It reviews current local changes, groups files into suggested include / review / exclude buckets, and drafts a commit message plus command sequence for the user to inspect.

`add-plan` is also read-only. `git add` remains dry-run unless `--apply` is present. By default it stages only files classified as safe to include; review files require `--include`, and excluded files require `--force-include`.

`git commit` is dry-run unless `--apply` is present. It only commits files that are already staged and will not automatically add unstaged or untracked files.

`git push` is dry-run unless `--apply` is present. It only runs a normal `git push` when the branch has an upstream, is ahead of upstream, and is not behind or diverged. Force push is not supported.

`git pull` is dry-run unless `--apply` is present. It only runs `git pull --ff-only` when the working tree is clean, the branch has an upstream, and the local branch is behind but not ahead or diverged.
