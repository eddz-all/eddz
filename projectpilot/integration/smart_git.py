from __future__ import annotations

from pathlib import Path
from typing import Any

from projectpilot.git.commit_planner import build_commit_plan
from projectpilot.git.doctor import build_doctor_report
from projectpilot.git.inspector import NotGitRepositoryError, inspect_repository
from projectpilot.git.state_map import build_state_map
from projectpilot.git.sync_planner import build_sync_plan

SCHEMA_VERSION = "smart-git.v1"
DEFAULT_ANALYSES = ["status", "doctor", "map", "sync_plan", "commit_plan"]
SUPPORTED_ANALYSES = {
    "status",
    "doctor",
    "map",
    "sync_plan",
    "commit_plan",
}


def analyze_repository(project_path: str | Path, analyses: list[str] | None = None) -> dict[str, Any]:
    requested = normalize_analyses(analyses)
    unsupported = [item for item in requested if item not in SUPPORTED_ANALYSES]
    if unsupported:
        return failure(
            "unsupported_analysis",
            f"Unsupported smart Git analysis: {', '.join(unsupported)}",
            repo_path=str(project_path),
        )

    try:
        status = inspect_repository(Path(project_path))
        payload: dict[str, Any] = {
            "success": True,
            "schema_version": SCHEMA_VERSION,
            "repo_path": str(status.repo_path),
            "branch": status.branch,
            "upstream": status.upstream,
            "commit": status.commit,
            "risk": "low",
            "state": status.state,
            "reports": {},
            "operation_plans": [],
            "blocked_operations": [],
            "next_steps": [],
            "warnings": [],
        }

        if "status" in requested:
            payload["reports"]["status"] = status.to_dict()
        if "doctor" in requested:
            payload["reports"]["doctor"] = build_doctor_report(status.repo_path).to_dict()
        if "map" in requested:
            state_map = build_state_map(status.repo_path)
            payload["reports"]["map"] = state_map.to_dict()
            payload["next_steps"].extend(state_map.next_steps)
            payload["warnings"].extend(state_map.warnings)
            payload["risk"] = max_risk(payload["risk"], state_map.risk)
        if "sync_plan" in requested:
            sync_plan = build_sync_plan(status.repo_path)
            payload["reports"]["sync_plan"] = sync_plan.to_dict()
            payload["operation_plans"].extend(sync_plan.operation_plans)
            payload["blocked_operations"].extend([item.to_dict() for item in sync_plan.blocked_operations])
            payload["next_steps"].extend(sync_plan.next_steps)
            payload["warnings"].extend(sync_plan.warnings)
            payload["risk"] = max_risk(payload["risk"], sync_plan.risk)
        if "commit_plan" in requested:
            commit_plan = build_commit_plan(status.repo_path)
            payload["reports"]["commit_plan"] = commit_plan.to_dict()
            payload["warnings"].extend(commit_plan.warnings)

        payload["next_steps"] = unique_strings(payload["next_steps"])
        payload["warnings"] = unique_strings(payload["warnings"])
        payload["blocked_operations"] = unique_dicts(payload["blocked_operations"])
        payload["operation_plans"] = unique_dicts(payload["operation_plans"])
        return payload
    except NotGitRepositoryError as exc:
        return failure("not_git_repository", str(exc), repo_path=str(project_path))
    except FileNotFoundError as exc:
        if exc.filename == "git":
            return failure("git_not_installed", "Git command was not found.", repo_path=str(project_path))
        return failure("path_not_found", str(exc), repo_path=str(project_path))
    except Exception as exc:
        return failure("unknown_error", str(exc), repo_path=str(project_path))


def normalize_analyses(analyses: list[str] | None) -> list[str]:
    if not analyses:
        return list(DEFAULT_ANALYSES)
    normalized: list[str] = []
    for item in analyses:
        value = str(item).strip().replace("-", "_")
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def failure(error_type: str, message: str, repo_path: str | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "schema_version": SCHEMA_VERSION,
        "error_type": error_type,
        "message": message,
        "repo_path": repo_path,
    }


def max_risk(current: str, candidate: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def unique_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        marker = repr(sorted(item.items()))
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result

