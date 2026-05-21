from __future__ import annotations

from pathlib import Path

from projectpilot.git.commit_planner import build_commit_plan, suggest_commit_message
from projectpilot.git.inspector import inspect_repository
from projectpilot.models.commit_plan import CommitPlanItem
from projectpilot.models.git_status import GitStatus
from projectpilot.models.operation_plan import OperationPlan
from projectpilot.utils.shell import run_git


def build_add_plan(
    path: Path,
    include_paths: list[str] | None = None,
    force_include_paths: list[str] | None = None,
) -> OperationPlan:
    commit_plan = build_commit_plan(path)
    include_request = set(include_paths or [])
    force_request = set(force_include_paths or [])
    items_by_path = {item.path: item for item in [*commit_plan.include, *commit_plan.review, *commit_plan.exclude]}
    blockers: list[str] = []
    warnings = list(commit_plan.warnings)
    planned_paths: list[str] = []
    review_paths = [item.path for item in commit_plan.review]
    excluded_paths = [item.path for item in commit_plan.exclude]

    for requested in sorted(include_request | force_request):
        if requested not in items_by_path:
            blockers.append(f"Requested path is not changed or not visible to Git: {requested}")

    planned_paths.extend(addable_paths(commit_plan.include))

    for item in commit_plan.review:
        if item.path in include_request:
            planned_paths.append(item.path)
        else:
            warnings.append(f"Review file not staged by default: {item.path}")

    for item in commit_plan.exclude:
        if item.path in force_request:
            planned_paths.append(item.path)
            warnings.append(f"Force-including excluded path: {item.path}")
        else:
            warnings.append(f"Excluded file not staged by default: {item.path}")

    if not planned_paths and not blockers:
        blockers.append("No files are eligible to add.")

    command = ["git", "add", "--", *planned_paths] if planned_paths else []
    allowed = bool(planned_paths) and not blockers
    reason = build_add_reason(planned_paths, include_request, force_request)

    return OperationPlan(
        operation="add",
        repo_path=commit_plan.repo_path,
        risk="medium",
        allowed=allowed,
        requires_apply=True,
        command=command,
        reason=reason,
        blockers=blockers,
        warnings=warnings,
        planned_paths=planned_paths,
        review_paths=review_paths,
        excluded_paths=excluded_paths,
        rollback_commands=[["git", "restore", "--staged", "--", *planned_paths]] if allowed else [],
    )


def addable_paths(items: list[CommitPlanItem]) -> list[str]:
    return [item.path for item in items if item.status in {"unstaged", "staged+unstaged", "untracked"}]


def build_add_reason(planned_paths: list[str], include_request: set[str], force_request: set[str]) -> str:
    if not planned_paths:
        return "No files will be staged."
    if include_request or force_request:
        return "Stage default include files plus explicitly requested review or excluded files."
    return "Stage files that ProjectPilot classified as safe to include."


def build_commit_operation_plan(path: Path, message: str | None = None) -> OperationPlan:
    status = inspect_repository(path)
    commit_plan = build_commit_plan(path)
    staged_include = staged_items(commit_plan.include)
    staged_review = staged_items(commit_plan.review)
    staged_exclude = staged_items(commit_plan.exclude)
    staged_paths = [item.path for item in [*staged_include, *staged_review, *staged_exclude]]
    blockers: list[str] = []
    warnings: list[str] = []

    if status.state != "normal":
        blockers.append(f"Repository is in a {status.state} state.")
    if status.conflicted_files:
        blockers.append("Conflicted files must be resolved before committing.")
    if not staged_paths:
        blockers.append("No staged files are available to commit.")
    if staged_exclude:
        blockers.append("Excluded-category files are staged; unstage them before committing.")
    if status.unstaged_files:
        warnings.append("Unstaged changes will not be included in this commit.")
    if status.untracked_files:
        warnings.append("Untracked files will not be included in this commit.")
    for item in staged_review:
        warnings.append(f"Review-category file is staged: {item.path}")

    suggested_message = clean_message(message) or suggest_commit_message(staged_include, staged_review)
    if staged_paths and not suggested_message:
        blockers.append("A commit message is required.")

    command = ["git", "commit", "-m", suggested_message] if suggested_message and staged_paths else []

    return OperationPlan(
        operation="commit",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=bool(staged_paths) and not blockers,
        requires_apply=True,
        command=command,
        reason=build_commit_reason(staged_paths, suggested_message),
        suggested_message=suggested_message,
        blockers=blockers,
        warnings=warnings,
        planned_paths=staged_paths,
        review_paths=[item.path for item in staged_review],
        excluded_paths=[item.path for item in staged_exclude],
        rollback_commands=[["git", "reset", "--soft", "HEAD~1"]] if staged_paths and not blockers else [],
    )


def staged_items(items: list[CommitPlanItem]) -> list[CommitPlanItem]:
    return [item for item in items if item.status in {"staged", "staged+unstaged"}]


def clean_message(message: str | None) -> str | None:
    if message is None:
        return None
    cleaned = message.strip()
    return cleaned or None


def build_commit_reason(staged_paths: list[str], suggested_message: str | None) -> str:
    if not staged_paths:
        return "No commit will be created because no files are staged."
    if suggested_message:
        return "Create a commit from currently staged files only."
    return "A commit message is needed before a commit can be created."


def build_push_operation_plan(path: Path) -> OperationPlan:
    status = inspect_repository(path)
    blockers: list[str] = []
    warnings: list[str] = []
    planned_refs: list[str] = []

    if status.state != "normal":
        blockers.append(f"Repository is in a {status.state} state.")
    if status.conflicted_files:
        blockers.append("Conflicted files must be resolved before pushing.")
    if status.branch is None:
        blockers.append("Detached HEAD cannot be pushed safely by ProjectPilot.")
    if not status.remotes:
        blockers.append("No Git remotes are configured for this repository.")
    if status.upstream is None:
        blockers.append("The current branch has no upstream branch configured.")
    if status.ahead > 0 and status.behind > 0:
        blockers.append("Local and upstream branches have diverged; push is blocked.")
    elif status.behind > 0:
        blockers.append("Local branch is behind upstream; fetch or pull before pushing.")
    elif status.ahead == 0 and status.upstream is not None:
        blockers.append("No local commits are ahead of upstream.")

    if status.staged_files:
        warnings.append("Staged but uncommitted files will not be pushed.")
    if status.unstaged_files:
        warnings.append("Unstaged changes will not be pushed.")
    if status.untracked_files:
        warnings.append("Untracked files will not be pushed.")

    if status.branch and status.upstream:
        planned_refs.append(f"{status.branch} -> {status.upstream}")

    command = ["git", "push"] if status.ahead > 0 and not blockers else []

    return OperationPlan(
        operation="push",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=bool(command) and not blockers,
        requires_apply=True,
        command=command,
        reason=build_push_reason(status.ahead, status.behind, status.upstream),
        blockers=blockers,
        warnings=warnings,
        planned_paths=planned_refs,
    )


def build_push_reason(ahead: int, behind: int, upstream: str | None) -> str:
    if upstream is None:
        return "No push will run because the branch has no upstream."
    if ahead > 0 and behind == 0:
        return f"Push {ahead} local commit(s) to upstream."
    if ahead > 0 and behind > 0:
        return "No push will run because local and upstream history diverged."
    if behind > 0:
        return "No push will run because local branch is behind upstream."
    return "No push will run because there are no local commits to push."


def build_pull_operation_plan(path: Path) -> OperationPlan:
    status = inspect_repository(path)
    blockers: list[str] = []
    warnings: list[str] = []
    planned_refs: list[str] = []

    if status.state != "normal":
        blockers.append(f"Repository is in a {status.state} state.")
    if status.conflicted_files:
        blockers.append("Conflicted files must be resolved before pulling.")
    if status.branch is None:
        blockers.append("Detached HEAD cannot be pulled safely by ProjectPilot.")
    if not status.remotes:
        blockers.append("No Git remotes are configured for this repository.")
    if status.upstream is None:
        blockers.append("The current branch has no upstream branch configured.")
    if status.staged_files or status.unstaged_files or status.untracked_files:
        blockers.append("Working tree must be clean before pulling.")
    if status.ahead > 0 and status.behind > 0:
        blockers.append("Local and upstream branches have diverged; pull is blocked.")
    elif status.ahead > 0:
        blockers.append("Local branch is ahead of upstream; push or inspect history before pulling.")
    elif status.behind == 0 and status.upstream is not None:
        blockers.append("No upstream commits are available to pull.")

    if status.branch and status.upstream:
        planned_refs.append(f"{status.upstream} -> {status.branch}")

    command = ["git", "pull", "--ff-only"] if status.behind > 0 and not blockers else []

    return OperationPlan(
        operation="pull",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=bool(command) and not blockers,
        requires_apply=True,
        command=command,
        reason=build_pull_reason(status.ahead, status.behind, status.upstream),
        blockers=blockers,
        warnings=warnings,
        planned_paths=planned_refs,
        rollback_commands=[["git", "reset", "--hard", status.commit]] if status.commit and command else [],
    )


def build_pull_reason(ahead: int, behind: int, upstream: str | None) -> str:
    if upstream is None:
        return "No pull will run because the branch has no upstream."
    if ahead > 0 and behind > 0:
        return "No pull will run because local and upstream history diverged."
    if ahead > 0:
        return "No pull will run because local branch is ahead of upstream."
    if behind > 0:
        return f"Fast-forward pull {behind} upstream commit(s)."
    return "No pull will run because there are no upstream commits to pull."


def build_switch_operation_plan(
    path: Path,
    target: str,
    create: bool = False,
    start_point: str | None = None,
) -> OperationPlan:
    status = inspect_repository(path)
    blockers = normal_state_blockers(status)
    warnings: list[str] = []

    if status.staged_files or status.unstaged_files or status.untracked_files:
        blockers.append("Working tree must be clean before switching branches.")
    if create:
        if not is_valid_branch_name(status.repo_path, target):
            blockers.append(f"Invalid branch name: {target}")
        if local_branch_exists(status.repo_path, target):
            blockers.append(f"Branch already exists: {target}")
        if start_point and not ref_exists(status.repo_path, start_point):
            blockers.append(f"Start point does not exist: {start_point}")
        command = ["git", "switch", "-c", target]
        if start_point:
            command.append(start_point)
        reason = f"Create and switch to branch '{target}'."
    else:
        if not local_branch_exists(status.repo_path, target):
            blockers.append(f"Local branch does not exist: {target}")
        command = ["git", "switch", target]
        reason = f"Switch to local branch '{target}'."

    rollback = [["git", "switch", status.branch]] if status.branch else []

    return OperationPlan(
        operation="switch",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=not blockers,
        requires_apply=True,
        command=command if not blockers else [],
        reason=reason,
        blockers=blockers,
        warnings=warnings,
        planned_paths=[target],
        rollback_commands=rollback if not blockers else [],
    )


def build_merge_operation_plan(path: Path, source: str) -> OperationPlan:
    status = inspect_repository(path)
    blockers = normal_state_blockers(status)
    warnings: list[str] = []
    changed_paths: list[str] = []

    if status.branch is None:
        blockers.append("Detached HEAD cannot be merged safely by ProjectPilot.")
    if status.staged_files or status.unstaged_files or status.untracked_files:
        blockers.append("Working tree must be clean before merging.")
    if not ref_exists(status.repo_path, source):
        blockers.append(f"Merge source does not exist: {source}")
    elif status.commit:
        if is_ancestor(status.repo_path, "HEAD", source):
            changed_paths = diff_name_only(status.repo_path, f"HEAD...{source}")
        elif is_ancestor(status.repo_path, source, "HEAD"):
            blockers.append(f"Current branch already contains {source}.")
        else:
            blockers.append("Only fast-forward merges are currently executable; non-fast-forward merge needs manual review.")
            changed_paths = diff_name_only(status.repo_path, f"HEAD...{source}")

    command = ["git", "merge", "--ff-only", source] if not blockers else []

    return OperationPlan(
        operation="merge",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=bool(command),
        requires_apply=True,
        command=command,
        reason=build_merge_reason(source, bool(command)),
        blockers=blockers,
        warnings=warnings,
        planned_paths=changed_paths,
        rollback_commands=[["git", "reset", "--hard", status.commit]] if status.commit and command else [],
    )


def build_stash_operation_plan(
    path: Path,
    message: str | None = None,
    include_untracked: bool = False,
) -> OperationPlan:
    status = inspect_repository(path)
    blockers = normal_state_blockers(status)
    warnings: list[str] = []
    changed_paths = [*status.staged_files, *status.unstaged_files]

    if include_untracked:
        changed_paths.extend(status.untracked_files)
    elif status.untracked_files:
        warnings.append("Untracked files will not be stashed unless --include-untracked is used.")

    if not status.staged_files and not status.unstaged_files and not (include_untracked and status.untracked_files):
        blockers.append("No local changes are available to stash.")

    stash_message = clean_message(message) or "ProjectPilot stash"
    command = ["git", "stash", "push", "-m", stash_message]
    if include_untracked:
        command.insert(3, "--include-untracked")

    return OperationPlan(
        operation="stash",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=not blockers,
        requires_apply=True,
        command=command if not blockers else [],
        reason="Save current local changes into a Git stash.",
        suggested_message=stash_message,
        blockers=blockers,
        warnings=warnings,
        planned_paths=dedupe(changed_paths),
        rollback_commands=[["git", "stash", "pop"]] if not blockers else [],
    )


def build_tag_operation_plan(path: Path, name: str, message: str | None = None) -> OperationPlan:
    status = inspect_repository(path)
    blockers = normal_state_blockers(status)
    warnings: list[str] = []

    if not is_valid_tag_name(status.repo_path, name):
        blockers.append(f"Invalid tag name: {name}")
    if tag_exists(status.repo_path, name):
        blockers.append(f"Tag already exists: {name}")
    if not status.is_clean:
        warnings.append("Working tree is dirty; the tag will still point at the current commit.")

    cleaned_message = clean_message(message)
    command = ["git", "tag", name] if cleaned_message is None else ["git", "tag", "-a", name, "-m", cleaned_message]

    return OperationPlan(
        operation="tag",
        repo_path=str(status.repo_path),
        risk="medium",
        allowed=not blockers,
        requires_apply=True,
        command=command if not blockers else [],
        reason=f"Create tag '{name}' at the current commit.",
        suggested_message=cleaned_message,
        blockers=blockers,
        warnings=warnings,
        planned_paths=[name],
        rollback_commands=[["git", "tag", "-d", name]] if not blockers else [],
    )


def build_revert_operation_plan(path: Path, revision: str, commit: bool = False) -> OperationPlan:
    status = inspect_repository(path)
    blockers = clean_history_operation_blockers(status, revision, "revert")
    command = ["git", "revert", revision]
    reason = f"Revert commit '{revision}'"
    if commit:
        command.insert(2, "--no-edit")
        reason += " and create a revert commit."
    else:
        command.insert(2, "--no-commit")
        reason += " without committing, so the result can be reviewed."

    return OperationPlan(
        operation="revert",
        repo_path=str(status.repo_path),
        risk="high" if commit else "medium",
        allowed=not blockers,
        requires_apply=True,
        command=command if not blockers else [],
        reason=reason,
        blockers=blockers,
        planned_paths=[revision],
        rollback_commands=[["git", "reset", "--hard", status.commit]] if status.commit and not blockers else [],
    )


def build_cherry_pick_operation_plan(path: Path, revision: str, commit: bool = False) -> OperationPlan:
    status = inspect_repository(path)
    blockers = clean_history_operation_blockers(status, revision, "cherry-pick")
    command = ["git", "cherry-pick", revision]
    reason = f"Cherry-pick commit '{revision}'"
    if commit:
        reason += " and create a commit."
    else:
        command.insert(2, "--no-commit")
        reason += " without committing, so the result can be reviewed."

    return OperationPlan(
        operation="cherry-pick",
        repo_path=str(status.repo_path),
        risk="high" if commit else "medium",
        allowed=not blockers,
        requires_apply=True,
        command=command if not blockers else [],
        reason=reason,
        blockers=blockers,
        planned_paths=[revision],
        rollback_commands=[["git", "reset", "--hard", status.commit]] if status.commit and not blockers else [],
    )


def build_high_risk_operation_plan(path: Path, operation: str, reason: str, command: list[str]) -> OperationPlan:
    status = inspect_repository(path)
    return OperationPlan(
        operation=operation,
        repo_path=str(status.repo_path),
        risk="high",
        allowed=False,
        requires_apply=True,
        command=[],
        reason=reason,
        blockers=[
            "ProjectPilot will not run this operation yet.",
            "This operation can discard work, rewrite history, or affect other collaborators.",
        ],
        warnings=["Manual execution should only happen after creating a backup or recovery plan."],
        planned_paths=[" ".join(command)],
    )


def normal_state_blockers(status: GitStatus) -> list[str]:
    blockers: list[str] = []
    if status.state != "normal":
        blockers.append(f"Repository is in a {status.state} state.")
    if status.conflicted_files:
        blockers.append("Conflicted files must be resolved first.")
    return blockers


def clean_history_operation_blockers(status: GitStatus, revision: str, operation: str) -> list[str]:
    blockers = normal_state_blockers(status)
    if status.staged_files or status.unstaged_files or status.untracked_files:
        blockers.append(f"Working tree must be clean before {operation}.")
    if not ref_exists(status.repo_path, revision):
        blockers.append(f"Revision does not exist: {revision}")
    elif is_merge_commit(status.repo_path, revision):
        blockers.append(f"Merge commits need an explicit mainline and are not handled by this {operation} workflow yet.")
    return blockers


def ref_exists(repo_path: Path, ref: str) -> bool:
    result = run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=repo_path, check=False)
    return result.returncode == 0


def local_branch_exists(repo_path: Path, branch: str) -> bool:
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo_path, check=False)
    return result.returncode == 0


def tag_exists(repo_path: Path, tag: str) -> bool:
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/tags/{tag}"], cwd=repo_path, check=False)
    return result.returncode == 0


def is_valid_branch_name(repo_path: Path, name: str) -> bool:
    result = run_git(["check-ref-format", "--branch", name], cwd=repo_path, check=False)
    return result.returncode == 0


def is_valid_tag_name(repo_path: Path, name: str) -> bool:
    result = run_git(["check-ref-format", f"refs/tags/{name}"], cwd=repo_path, check=False)
    return result.returncode == 0


def is_ancestor(repo_path: Path, ancestor: str, descendant: str) -> bool:
    result = run_git(["merge-base", "--is-ancestor", ancestor, descendant], cwd=repo_path, check=False)
    return result.returncode == 0


def is_merge_commit(repo_path: Path, revision: str) -> bool:
    result = run_git(["rev-list", "--parents", "-n", "1", revision], cwd=repo_path, check=False)
    if result.returncode != 0:
        return False
    return len(result.stdout.strip().split()) > 2


def diff_name_only(repo_path: Path, revision_range: str) -> list[str]:
    result = run_git(["diff", "--name-only", revision_range], cwd=repo_path, check=False)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def build_merge_reason(source: str, allowed: bool) -> str:
    if allowed:
        return f"Fast-forward merge '{source}' into the current branch."
    return f"Inspect merge readiness for '{source}'."


def dedupe(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(paths))
