from __future__ import annotations

import shlex
from pathlib import PurePosixPath

from projectpilot.git.inspector import inspect_repository
from projectpilot.models.commit_plan import CommitPlan, CommitPlanItem
from projectpilot.models.git_status import GitStatus


SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".css",
    ".scss",
    ".html",
}
DOC_EXTENSIONS = {".md", ".rst", ".txt"}
CONFIG_FILENAMES = {
    ".gitignore",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    "requirements.txt",
    "Dockerfile",
    "Makefile",
}
REVIEW_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
}
EXCLUDE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".projectpilot",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".swp", ".DS_Store"}


def build_commit_plan(path) -> CommitPlan:
    status = inspect_repository(path)
    include: list[CommitPlanItem] = []
    review: list[CommitPlanItem] = []
    exclude: list[CommitPlanItem] = []
    warnings = build_plan_warnings(status)

    for item in collect_plan_items(status):
        if item.category == "include":
            include.append(item)
        elif item.category == "exclude":
            exclude.append(item)
        else:
            review.append(item)

    suggested_message = suggest_commit_message(include, review)
    suggested_commands = build_suggested_commands(include, review, suggested_message)
    summary = build_summary(include, review, exclude)

    return CommitPlan(
        repo_path=str(status.repo_path),
        branch=status.branch,
        summary=summary,
        suggested_message=suggested_message,
        include=include,
        review=review,
        exclude=exclude,
        warnings=warnings,
        suggested_commands=suggested_commands,
    )


def collect_plan_items(status: GitStatus) -> list[CommitPlanItem]:
    items: list[CommitPlanItem] = []
    seen: set[str] = set()

    for change in status.changed_files:
        if change.is_staged and change.is_unstaged:
            item_status = "staged+unstaged"
        elif change.is_staged:
            item_status = "staged"
        else:
            item_status = "unstaged"
        items.append(classify_path(change.path, item_status))
        seen.add(change.path)
    for path in status.untracked_files:
        if path not in seen:
            items.append(classify_path(path, "untracked"))
            seen.add(path)
    for path in status.conflicted_files:
        if path not in seen:
            items.append(
                CommitPlanItem(
                    path=path,
                    status="conflicted",
                    category="review",
                    reason="Conflicted files need manual resolution before they can be committed.",
                )
            )

    return items


def classify_path(path: str, status: str) -> CommitPlanItem:
    normalized = path.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    parts = set(pure_path.parts)
    name = pure_path.name
    suffix = pure_path.suffix

    if parts & EXCLUDE_PARTS or name in EXCLUDE_SUFFIXES or suffix in EXCLUDE_SUFFIXES:
        return CommitPlanItem(
            path=path,
            status=status,
            category="exclude",
            reason="Looks like generated, cached, build, or local-only output.",
        )

    if name in REVIEW_FILENAMES:
        return CommitPlanItem(
            path=path,
            status=status,
            category="review",
            reason="Lock files can be correct, but should be checked against dependency changes.",
        )

    if name in CONFIG_FILENAMES:
        return CommitPlanItem(
            path=path,
            status=status,
            category="include",
            reason="Project configuration changes usually belong in the commit.",
        )

    if pure_path.parts and pure_path.parts[0] in {"tests", "test"}:
        return CommitPlanItem(
            path=path,
            status=status,
            category="include",
            reason="Test changes usually belong with the implementation they verify.",
        )

    if suffix in SOURCE_EXTENSIONS:
        return CommitPlanItem(
            path=path,
            status=status,
            category="include",
            reason="Source file changes are usually part of the intended implementation.",
        )

    if suffix in DOC_EXTENSIONS:
        return CommitPlanItem(
            path=path,
            status=status,
            category="include",
            reason="Documentation changes are safe to include after review.",
        )

    return CommitPlanItem(
        path=path,
        status=status,
        category="review",
        reason="File type is not recognized by the current rules, so review it before adding.",
    )


def build_plan_warnings(status: GitStatus) -> list[str]:
    warnings: list[str] = []
    if status.state != "normal":
        warnings.append(f"Repository is in a {status.state} state; finish that operation before committing.")
    if status.conflicted_files:
        warnings.append("Conflicted files must be resolved before creating a commit.")
    if not status.staged_files and not status.unstaged_files and not status.untracked_files and not status.conflicted_files:
        warnings.append("There are no local changes to commit.")
    if status.untracked_files:
        warnings.append("Untracked files are included in the plan, but should be reviewed before adding.")
    return warnings


def suggest_commit_message(include: list[CommitPlanItem], review: list[CommitPlanItem]) -> str | None:
    candidates = include or review
    if not candidates:
        return None

    paths = [PurePosixPath(item.path.replace("\\", "/")) for item in candidates]
    top_levels = {path.parts[0] for path in paths if path.parts}
    suffixes = {path.suffix for path in paths}

    if top_levels <= {"tests", "test"}:
        return "Update Git intelligence tests"
    if "projectpilot" in top_levels and "tests" in top_levels:
        return "Update intelligent Git assistant"
    if "projectpilot" in top_levels:
        return "Update intelligent Git assistant"
    if suffixes and suffixes <= DOC_EXTENSIONS:
        return "Update documentation"
    if any(path.name in CONFIG_FILENAMES for path in paths):
        return "Update project configuration"
    return "Update project files"


def build_suggested_commands(
    include: list[CommitPlanItem],
    review: list[CommitPlanItem],
    suggested_message: str | None,
) -> list[str]:
    commands: list[str] = ["git diff", "git status --short"]
    include_paths = [item.path for item in include]
    review_paths = [item.path for item in review]

    if include_paths:
        commands.append("git add " + " ".join(shlex.quote(path) for path in include_paths))
    if review_paths:
        commands.append("# Review before adding: " + " ".join(shlex.quote(path) for path in review_paths))
    if suggested_message:
        commands.append("git commit -m " + shlex.quote(suggested_message))

    return commands


def build_summary(
    include: list[CommitPlanItem],
    review: list[CommitPlanItem],
    exclude: list[CommitPlanItem],
) -> str:
    total = len(include) + len(review) + len(exclude)
    if total == 0:
        return "No local changes found."
    return (
        f"Found {total} changed file(s): "
        f"{len(include)} suggested to include, "
        f"{len(review)} to review, "
        f"{len(exclude)} suggested to exclude."
    )
