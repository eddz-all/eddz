from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if (REPO_ROOT / "projectpilot").exists() and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from projectpilot.git.inspector import NotGitRepositoryError, find_repo_root, inspect_repository


MAX_COMMITS = 40


def _run_git(args: list[str], cwd: Path, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=error.stdout or "",
            stderr=error.stderr or "Git command timed out",
        )


def _split_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.strip()]


def _short_ref_name(name: str) -> str:
    for prefix in ("refs/heads/", "refs/remotes/", "refs/tags/"):
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return name


def _ref_type(name: str) -> str:
    if name.startswith("refs/heads/"):
        return "branch"
    if name.startswith("refs/remotes/"):
        return "remote"
    if name.startswith("refs/tags/"):
        return "tag"
    return "ref"


def _load_refs(repo_path: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    result = _run_git(
        [
            "for-each-ref",
            "--format=%(refname)%09%(objectname)%09%(HEAD)%09%(upstream:short)",
            "refs/heads",
            "refs/remotes",
            "refs/tags",
        ],
        repo_path,
    )
    refs: list[dict] = []
    refs_by_commit: dict[str, list[dict]] = {}
    if result.returncode != 0:
        return refs, refs_by_commit

    for line in _split_lines(result.stdout):
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        refname, target = parts[0], parts[1]
        is_head = len(parts) > 2 and parts[2] == "*"
        upstream = parts[3] if len(parts) > 3 and parts[3] else None
        ref = {
            "name": _short_ref_name(refname),
            "full_name": refname,
            "type": _ref_type(refname),
            "target": target,
            "is_head": is_head,
            "upstream": upstream,
        }
        refs.append(ref)
        refs_by_commit.setdefault(target, []).append(ref)

    return refs, refs_by_commit


def _load_commits(repo_path: Path, refs_by_commit: dict[str, list[dict]]) -> list[dict]:
    result = _run_git(
        [
            "log",
            "--all",
            f"--max-count={MAX_COMMITS}",
            "--date=relative",
            "--pretty=format:%H%x1f%P%x1f%an%x1f%ar%x1f%s",
        ],
        repo_path,
    )
    if result.returncode != 0:
        return []

    commits: list[dict] = []
    for index, line in enumerate(_split_lines(result.stdout)):
        parts = line.split("\x1f")
        if len(parts) < 5:
            continue
        commit_hash, parents_raw, author, relative_time, subject = parts[:5]
        parents = [parent for parent in parents_raw.split() if parent]
        commit_refs = refs_by_commit.get(commit_hash, [])
        commits.append(
            {
                "hash": commit_hash,
                "short_hash": commit_hash[:7],
                "parents": parents,
                "subject": subject,
                "author": author,
                "relative_time": relative_time,
                "refs": commit_refs,
                "lane": min(index % 4, len(parents)),
                "is_merge": len(parents) > 1,
                "is_head": any(ref.get("is_head") for ref in commit_refs),
            }
        )
    return commits


def _load_graph_text(repo_path: Path) -> list[str]:
    result = _run_git(
        [
            "log",
            "--graph",
            "--decorate",
            "--oneline",
            "--all",
            f"--max-count={MAX_COMMITS}",
        ],
        repo_path,
    )
    if result.returncode != 0:
        return []
    return _split_lines(result.stdout)


def _worktree_payload(status) -> dict:
    changes = [item.to_dict() for item in status.changed_files]
    return {
        "is_clean": status.is_clean,
        "state": status.state,
        "staged_files": status.staged_files,
        "unstaged_files": status.unstaged_files,
        "untracked_files": status.untracked_files,
        "conflicted_files": status.conflicted_files,
        "changed_files": changes,
        "counts": {
            "staged": len(status.staged_files),
            "unstaged": len(status.unstaged_files),
            "untracked": len(status.untracked_files),
            "conflicted": len(status.conflicted_files),
        },
    }


def inspect_git_worktree(project_path: str) -> dict:
    try:
        repo_path = find_repo_root(Path(project_path))
        status = inspect_repository(repo_path)
    except (NotGitRepositoryError, OSError, subprocess.SubprocessError) as error:
        return {
            "success": False,
            "project_path": project_path,
            "message": str(error),
            "commits": [],
            "refs": [],
            "graph_text": [],
            "worktree": {
                "is_clean": False,
                "state": "unavailable",
                "staged_files": [],
                "unstaged_files": [],
                "untracked_files": [],
                "conflicted_files": [],
                "changed_files": [],
                "counts": {"staged": 0, "unstaged": 0, "untracked": 0, "conflicted": 0},
            },
        }

    refs, refs_by_commit = _load_refs(repo_path)
    commits = _load_commits(repo_path, refs_by_commit)
    remote_urls = sorted({url for urls in status.remotes.values() for url in urls})

    return {
        "success": True,
        "project_path": project_path,
        "repo_path": str(repo_path),
        "branch": status.branch,
        "upstream": status.upstream,
        "commit": status.commit,
        "ahead": status.ahead,
        "behind": status.behind,
        "state": status.state,
        "remote_urls": remote_urls,
        "refs": refs,
        "commits": commits,
        "graph_text": _load_graph_text(repo_path),
        "worktree": _worktree_payload(status),
    }
