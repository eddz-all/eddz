from __future__ import annotations

from pathlib import Path

from projectpilot.git.inspector import inspect_repository
from projectpilot.models.git_status import GitStatus
from projectpilot.models.state_map import GitStateMap, LocalCommitSummary, RemoteSummary, StateMapFile
from projectpilot.utils.shell import run_git


def build_state_map(path: Path) -> GitStateMap:
    status = inspect_repository(path)
    return GitStateMap(
        repo_path=str(status.repo_path),
        branch=status.branch,
        upstream=status.upstream,
        commit=status.commit,
        state=status.state,
        risk=state_map_risk(status),
        working_tree=working_tree_files(status),
        staged=staged_files(status),
        untracked=[StateMapFile(path=item, status="??", area="untracked") for item in status.untracked_files],
        conflicted=[StateMapFile(path=item, status="UU", area="conflicted") for item in status.conflicted_files],
        local_commits=LocalCommitSummary(ahead=status.ahead, commits=local_commit_summaries(status)),
        remote=RemoteSummary(
            has_upstream=status.upstream is not None,
            upstream=status.upstream,
            behind=status.behind,
            diverged=is_diverged(status),
        ),
        next_steps=state_map_next_steps(status),
        warnings=state_map_warnings(status),
    )


def working_tree_files(status: GitStatus) -> list[StateMapFile]:
    return [
        StateMapFile(path=item.path, status=item.worktree_status, area="working_tree")
        for item in status.changed_files
        if item.is_unstaged
    ]


def staged_files(status: GitStatus) -> list[StateMapFile]:
    return [
        StateMapFile(path=item.path, status=item.index_status, area="staged")
        for item in status.changed_files
        if item.is_staged
    ]


def local_commit_summaries(status: GitStatus) -> list[str]:
    if not status.upstream or status.ahead <= 0:
        return []
    result = run_git(
        ["log", "--oneline", "--decorate=no", f"{status.upstream}..HEAD"],
        cwd=status.repo_path,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def state_map_risk(status: GitStatus) -> str:
    if status.conflicted_files or status.state != "normal" or is_diverged(status):
        return "high"
    if not status.upstream or not status.is_clean or status.ahead > 0 or status.behind > 0:
        return "medium"
    return "low"


def state_map_next_steps(status: GitStatus) -> list[str]:
    steps: list[str] = []
    if status.conflicted_files:
        steps.append("Resolve conflicted files, stage them, then continue the current Git operation.")
        return steps
    if status.state != "normal":
        steps.append(f"Finish or abort the current {status.state} operation before starting another Git action.")
        return steps
    if status.staged_files:
        steps.append("Review the commit plan before creating a commit.")
    if status.unstaged_files or status.untracked_files:
        steps.append("Review working tree changes and stage related files.")
    if not status.upstream:
        steps.append("Set an upstream branch before push or pull.")
    elif is_diverged(status):
        steps.append("Fetch and choose merge or rebase before pushing.")
    elif status.behind > 0 and status.is_clean:
        steps.append("Fast-forward pull is available.")
    elif status.behind > 0:
        steps.append("Commit or stash local changes before pulling upstream commits.")
    elif status.ahead > 0:
        steps.append("Push local commits when ready.")
    if not steps:
        steps.append("No Git action needed right now.")
    return steps


def state_map_warnings(status: GitStatus) -> list[str]:
    warnings: list[str] = []
    if not status.remotes:
        warnings.append("No Git remote is configured.")
    if not status.upstream:
        warnings.append("Current branch has no upstream branch configured.")
    if is_diverged(status):
        warnings.append("Local and upstream branches have diverged.")
    return warnings


def is_diverged(status: GitStatus) -> bool:
    return status.ahead > 0 and status.behind > 0

