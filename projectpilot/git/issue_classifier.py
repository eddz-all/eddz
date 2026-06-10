from __future__ import annotations

from dataclasses import asdict, dataclass, field

from projectpilot.git.commit_planner import build_commit_plan
from projectpilot.models.commit_plan import CommitPlan
from projectpilot.models.git_status import GitStatus


@dataclass(frozen=True)
class GitRepairOption:
    label: str
    command: list[str]
    risk: str = "low"
    requires_approval: bool = False
    destructive: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GitIssue:
    code: str
    title: str
    category: str
    severity: str
    active: bool
    summary: str
    evidence: list[str] = field(default_factory=list)
    repair_options: list[GitRepairOption] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["repair_options"] = [item.to_dict() for item in self.repair_options]
        return data


def classify_git_issues(status: GitStatus, commit_plan: CommitPlan | None = None) -> dict:
    plan = commit_plan or build_commit_plan(status.repo_path)
    playbook = [
        conflict_issue(status),
        wrong_branch_issue(status),
        local_changes_block_issue(status),
        push_rejected_issue(status),
        complex_history_issue(status),
        accidental_files_issue(status, plan),
        gitignore_issue(status, plan),
        detached_head_issue(status),
        force_push_issue(status),
        unknown_state_issue(status),
    ]
    issues = [item for item in playbook if item.active]

    return {
        "schema_version": "git-issues.v1",
        "summary": build_issue_summary(issues),
        "issues": [item.to_dict() for item in issues],
        "playbook": [item.to_dict() for item in playbook],
    }


def conflict_issue(status: GitStatus) -> GitIssue:
    active = bool(status.conflicted_files) or status.state in {"conflict", "merge", "rebase"}
    evidence = []
    if status.state != "normal":
        evidence.append(f"repository state: {status.state}")
    if status.conflicted_files:
        evidence.append(f"conflicted files: {', '.join(status.conflicted_files[:5])}")
    return GitIssue(
        code="merge_conflict",
        title="Merge conflict",
        category="conflict",
        severity="high" if active else "low",
        active=active,
        summary="Resolve conflicted files, stage them, then continue merge or rebase.",
        evidence=evidence,
        repair_options=[
            GitRepairOption("Inspect conflicts", ["git", "status"], notes=["Review files marked as unmerged."]),
            GitRepairOption("Stage resolved files", ["git", "add", "--", "<resolved-files>"], requires_approval=True),
            GitRepairOption("Continue rebase", ["git", "rebase", "--continue"], risk="medium", requires_approval=True),
            GitRepairOption("Complete merge commit", ["git", "commit"], risk="medium", requires_approval=True),
        ],
        guardrails=["Do not pull, push, or switch branches until conflicts are resolved."],
    )


def wrong_branch_issue(status: GitStatus) -> GitIssue:
    active = status.branch is not None and status.branch not in {"main", "master"}
    branch = status.branch or "detached HEAD"
    return GitIssue(
        code="wrong_branch",
        title="Wrong branch risk",
        category="branch",
        severity="medium" if active else "low",
        active=active,
        summary="Confirm the target branch before committing, pushing, or deploying.",
        evidence=[f"current branch: {branch}"],
        repair_options=[
            GitRepairOption("Check branch", ["git", "branch", "--show-current"]),
            GitRepairOption("Protect current work", ["git", "stash", "push", "--include-untracked", "-m", "ProjectPilot branch switch"], risk="medium", requires_approval=True),
            GitRepairOption("Switch branch", ["git", "switch", "<correct-branch>"], risk="medium", requires_approval=True),
        ],
        guardrails=["If work was committed on the wrong branch, create a cherry-pick plan instead of copying files manually."],
    )


def local_changes_block_issue(status: GitStatus) -> GitIssue:
    active = not status.is_clean and not status.conflicted_files
    evidence = changed_evidence(status)
    return GitIssue(
        code="local_changes_block",
        title="Local changes block pull or switch",
        category="working_tree",
        severity="medium" if active else "low",
        active=active,
        summary="Commit or stash local work before pull, rebase, merge, or branch switch.",
        evidence=evidence,
        repair_options=[
            GitRepairOption("Review diff", ["git", "diff"]),
            GitRepairOption("Create commit plan", ["projectpilot", "git", "commit-plan", str(status.repo_path)]),
            GitRepairOption("Stash safely", ["git", "stash", "push", "--include-untracked", "-m", "ProjectPilot safe stash"], risk="medium", requires_approval=True),
        ],
        guardrails=["Discard operations such as reset --hard or clean -fd require explicit approval."],
    )


def push_rejected_issue(status: GitStatus) -> GitIssue:
    active = status.behind > 0
    evidence = [f"ahead: {status.ahead}", f"behind: {status.behind}"]
    return GitIssue(
        code="push_rejected",
        title="Push rejected risk",
        category="sync",
        severity="high" if status.ahead > 0 and status.behind > 0 else "medium" if active else "low",
        active=active,
        summary="Remote contains commits missing locally; fetch and choose a safe sync strategy before pushing.",
        evidence=evidence,
        repair_options=[
            GitRepairOption("Fetch remote", ["git", "fetch", "--prune"]),
            GitRepairOption("Fast-forward pull", ["git", "pull", "--ff-only"], risk="medium", requires_approval=True),
            GitRepairOption("Rebase after review", ["git", "pull", "--rebase"], risk="high", requires_approval=True),
        ],
        guardrails=["Do not force push to solve rejection unless force-with-lease is explicitly approved."],
    )


def complex_history_issue(status: GitStatus) -> GitIssue:
    active = status.ahead > 0 and status.behind > 0
    return GitIssue(
        code="complex_history",
        title="History has diverged",
        category="history",
        severity="high" if active else "low",
        active=active,
        summary="Local and remote both have unique commits; choose merge or rebase intentionally.",
        evidence=[f"ahead: {status.ahead}", f"behind: {status.behind}"],
        repair_options=[
            GitRepairOption("Show graph", ["git", "log", "--oneline", "--graph", "--decorate", "--all"]),
            GitRepairOption("Merge strategy", ["git", "merge", "<upstream>"], risk="high", requires_approval=True),
            GitRepairOption("Rebase strategy", ["git", "rebase", "<upstream>"], risk="high", requires_approval=True),
        ],
        guardrails=["Team policy should decide merge vs rebase before applying either plan."],
    )


def accidental_files_issue(status: GitStatus, plan: CommitPlan) -> GitIssue:
    suspicious = suspicious_paths(status)
    excluded = [item.path for item in plan.exclude]
    active_paths = dedupe([*suspicious, *excluded])
    active = bool(active_paths)
    return GitIssue(
        code="accidental_files",
        title="Accidental file in commit",
        category="commit_hygiene",
        severity="high" if any(is_sensitive_path(path) for path in active_paths) else "medium" if active else "low",
        active=active,
        summary="Remove secrets, caches, generated outputs, or large artifacts from the commit plan.",
        evidence=active_paths[:8],
        repair_options=[
            GitRepairOption("Unstage file", ["git", "restore", "--staged", "--", "<file>"], risk="medium", requires_approval=True),
            GitRepairOption("Stop tracking file", ["git", "rm", "--cached", "<file>"], risk="medium", requires_approval=True),
            GitRepairOption("Amend recent commit", ["git", "commit", "--amend"], risk="high", requires_approval=True),
        ],
        guardrails=["Never commit .env, private keys, tokens, build output, caches, or local database files."],
    )


def gitignore_issue(status: GitStatus, plan: CommitPlan) -> GitIssue:
    tracked_ignored = [item.path for item in plan.exclude if item.status in {"staged", "unstaged", "staged+unstaged"}]
    active = bool(tracked_ignored)
    return GitIssue(
        code="gitignore_not_effective",
        title=".gitignore not effective",
        category="ignore_rules",
        severity="medium" if active else "low",
        active=active,
        summary="The file looks generated or local-only but is already tracked by Git.",
        evidence=tracked_ignored[:8],
        repair_options=[
            GitRepairOption("Check ignore rule", ["git", "check-ignore", "-v", "<file>"]),
            GitRepairOption("Stop tracking file", ["git", "rm", "--cached", "<file>"], risk="medium", requires_approval=True),
            GitRepairOption("Commit ignore update", ["git", "add", ".gitignore"], risk="medium", requires_approval=True),
        ],
        guardrails=["Removing from the index does not delete the local file unless a destructive remove is approved."],
    )


def detached_head_issue(status: GitStatus) -> GitIssue:
    active = status.branch is None
    return GitIssue(
        code="detached_head",
        title="Detached HEAD",
        category="branch",
        severity="high" if active else "low",
        active=active,
        summary="Create a branch before committing if you want to keep this work.",
        evidence=["HEAD is detached"] if active else [f"current branch: {status.branch}"],
        repair_options=[
            GitRepairOption("Create branch here", ["git", "switch", "-c", "<new-branch>"], risk="medium", requires_approval=True),
            GitRepairOption("Return to branch", ["git", "switch", "<branch>"], risk="medium", requires_approval=True),
        ],
        guardrails=["Do not commit further work on detached HEAD unless it is intentionally temporary."],
    )


def force_push_issue(status: GitStatus) -> GitIssue:
    active = status.ahead > 0 and status.behind > 0
    return GitIssue(
        code="force_push_risk",
        title="Force push risk",
        category="remote_safety",
        severity="high" if active else "low",
        active=active,
        summary="Force push can overwrite remote work; use force-with-lease only after reviewing remote commits.",
        evidence=[f"ahead: {status.ahead}", f"behind: {status.behind}"],
        repair_options=[
            GitRepairOption("Inspect remote work", ["git", "log", "--oneline", "--graph", "--decorate", "--all"]),
            GitRepairOption("Safer force push", ["git", "push", "--force-with-lease"], risk="high", requires_approval=True, destructive=True),
        ],
        guardrails=["Plain git push --force is blocked by ProjectPilot policy."],
    )


def unknown_state_issue(status: GitStatus) -> GitIssue:
    active = not status.upstream or not status.remotes
    evidence = []
    if not status.remotes:
        evidence.append("no remote configured")
    if not status.upstream:
        evidence.append("no upstream configured")
    if status.upstream:
        evidence.append(f"upstream: {status.upstream}")
    return GitIssue(
        code="unknown_state",
        title="Unknown current state",
        category="diagnostics",
        severity="medium" if active else "low",
        active=active,
        summary="Run the status, graph, and diff triage set before deciding on a write operation.",
        evidence=evidence,
        repair_options=[
            GitRepairOption("Status", ["git", "status"]),
            GitRepairOption("Graph", ["git", "log", "--oneline", "--graph", "--decorate", "--all"]),
            GitRepairOption("Diff", ["git", "diff"]),
        ],
        guardrails=["No write operation should be applied until the branch, upstream, and working tree state are known."],
    )


def build_issue_summary(issues: list[GitIssue]) -> str:
    if not issues:
        return "No active common Git issue detected."
    high = sum(1 for item in issues if item.severity == "high")
    medium = sum(1 for item in issues if item.severity == "medium")
    return f"{len(issues)} active Git issue(s): {high} high, {medium} medium."


def changed_evidence(status: GitStatus) -> list[str]:
    evidence = []
    if status.staged_files:
        evidence.append(f"staged: {len(status.staged_files)}")
    if status.unstaged_files:
        evidence.append(f"unstaged: {len(status.unstaged_files)}")
    if status.untracked_files:
        evidence.append(f"untracked: {len(status.untracked_files)}")
    return evidence


def suspicious_paths(status: GitStatus) -> list[str]:
    paths = [*status.staged_files, *status.unstaged_files, *status.untracked_files]
    return [path for path in paths if is_sensitive_path(path) or is_generated_path(path)]


def is_sensitive_path(path: str) -> bool:
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    return (
        name.startswith(".env")
        or "secret" in lowered
        or "password" in lowered
        or "token" in lowered
        or lowered.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def is_generated_path(path: str) -> bool:
    lowered = path.lower()
    parts = set(lowered.split("/"))
    return bool(
        parts & {"node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        or lowered.endswith((".pyc", ".pyo", ".log", ".tmp", ".swp", ".ds_store"))
    )


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
