from __future__ import annotations

from pathlib import Path

from projectpilot.git.parser import parse_branch_status, parse_remotes, parse_status_entries
from projectpilot.models.git_status import GitStatus
from projectpilot.utils.shell import CommandError, run_git


class NotGitRepositoryError(RuntimeError):
    pass


def inspect_repository(path: Path) -> GitStatus:
    repo_path = find_repo_root(path)
    porcelain = run_git(["status", "--porcelain=v2", "--branch", "--untracked-files=all"], cwd=repo_path).stdout
    branch = parse_branch_status(porcelain)
    changed_files, untracked_files, conflicted_files = parse_status_entries(porcelain)
    remotes = parse_remotes(run_git(["remote", "-v"], cwd=repo_path, check=False).stdout)

    staged_files = [item.path for item in changed_files if item.is_staged]
    unstaged_files = [item.path for item in changed_files if item.is_unstaged]
    state = detect_repository_state(repo_path, conflicted_files)
    is_clean = not staged_files and not unstaged_files and not untracked_files and not conflicted_files and state == "normal"

    return GitStatus(
        repo_path=repo_path,
        branch=branch["head"] if isinstance(branch["head"], str) else None,
        upstream=branch["upstream"] if isinstance(branch["upstream"], str) else None,
        commit=branch["commit"] if isinstance(branch["commit"], str) else None,
        is_clean=is_clean,
        ahead=int(branch["ahead"] or 0),
        behind=int(branch["behind"] or 0),
        staged_files=staged_files,
        unstaged_files=unstaged_files,
        untracked_files=untracked_files,
        conflicted_files=conflicted_files,
        changed_files=changed_files,
        remotes=remotes,
        state=state,
    )


def find_repo_root(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    try:
        result = run_git(["rev-parse", "--show-toplevel"], cwd=candidate)
    except CommandError as exc:
        raise NotGitRepositoryError(f"{candidate} is not inside a Git repository.") from exc
    return Path(result.stdout.strip()).resolve()


def detect_repository_state(repo_path: Path, conflicted_files: list[str]) -> str:
    git_dir_result = run_git(["rev-parse", "--git-dir"], cwd=repo_path)
    git_dir = Path(git_dir_result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = repo_path / git_dir

    if conflicted_files:
        return "conflict"
    if (git_dir / "MERGE_HEAD").exists():
        return "merge"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        return "rebase"
    if (git_dir / "CHERRY_PICK_HEAD").exists():
        return "cherry-pick"
    if (git_dir / "REVERT_HEAD").exists():
        return "revert"
    return "normal"
