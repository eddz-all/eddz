from pathlib import Path
import sys

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, Project, ProjectServerMapping, Server
from schemas import AIAnalyzeRequest, ConfigPlanRequest, GitAnalyzeRequest
from services.ai_service import build_mock_config_plan, build_mock_environment_analysis
from services.executor_task_service import create_executor_task
from services.formatters import format_environment_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
if (REPO_ROOT / "projectpilot").exists() and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from projectpilot.integration.smart_git import analyze_repository  # noqa: E402


router = APIRouter(tags=["ai"])


def _risk_rank(risk: str | None):
    return {"low": 0, "medium": 1, "high": 2}.get(risk or "low", 0)


def _max_risk(left: str, right: str | None):
    return right if _risk_rank(right) > _risk_rank(left) else left


def _merge_issue_reports(reports: list[dict]):
    issue_by_code = {}
    playbook_by_code = {}
    for report in reports:
        for issue in report.get("playbook") or []:
            existing = playbook_by_code.get(issue.get("code"))
            if existing is None:
                playbook_by_code[issue.get("code")] = {**issue, "evidence": list(issue.get("evidence") or [])}
            else:
                existing["active"] = bool(existing.get("active") or issue.get("active"))
                existing["severity"] = max(
                    [existing.get("severity", "low"), issue.get("severity", "low")],
                    key=_risk_rank,
                )
                existing["evidence"] = sorted(set(existing.get("evidence") or []) | set(issue.get("evidence") or []))
        for issue in report.get("issues") or []:
            existing = issue_by_code.get(issue.get("code"))
            if existing is None:
                issue_by_code[issue.get("code")] = {**issue, "evidence": list(issue.get("evidence") or [])}
            else:
                existing["severity"] = max(
                    [existing.get("severity", "low"), issue.get("severity", "low")],
                    key=_risk_rank,
                )
                existing["evidence"] = sorted(set(existing.get("evidence") or []) | set(issue.get("evidence") or []))

    issues = list(issue_by_code.values())
    playbook = list(playbook_by_code.values())
    high = sum(1 for issue in issues if issue.get("severity") == "high")
    medium = sum(1 for issue in issues if issue.get("severity") == "medium")
    summary = "No active common Git issue detected."
    if issues:
        summary = f"{len(issues)} active Git issue(s): {high} high, {medium} medium."
    return {
        "schema_version": "git-issues.v1",
        "summary": summary,
        "issues": issues,
        "playbook": playbook,
    }


@router.post("/projects/{project_id}/ai/analyze-env")
def analyze_project_environment(
    project_id: int,
    request: AIAnalyzeRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project_id)
        .all()
    )

    server_snapshots = []
    for binding, server in bindings:
        latest_snapshot = (
            db.query(EnvironmentSnapshot)
            .filter(
                EnvironmentSnapshot.project_id == project_id,
                EnvironmentSnapshot.server_id == server.id,
            )
            .order_by(EnvironmentSnapshot.id.desc())
            .first()
        )
        server_snapshots.append(
            {
                "binding_id": binding.id,
                "server": server,
                "server_name": server.name,
                "project_path": binding.project_path,
                "snapshot": latest_snapshot,
            }
        )

    analysis = build_mock_environment_analysis(server_snapshots)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "focus": request.focus,
        "question": request.question,
        "summary": analysis["summary"],
        "issues": analysis["issues"],
        "suggestions": analysis["suggestions"],
        "risk_level": analysis["risk_level"],
        "context": [
            {
                "binding_id": item["binding_id"],
                "server_id": item["server"].id,
                "server_name": item["server"].name,
                "connection_mode": item["server"].connection_mode,
                "project_path": item["project_path"],
                "latest_environment_snapshot": format_environment_snapshot(
                    item["snapshot"]
                ),
            }
            for item in server_snapshots
        ],
    }


@router.post("/projects/{project_id}/ai/config-plan")
def create_project_config_plan(
    project_id: int,
    request: ConfigPlanRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    target_server = db.query(Server).filter(Server.id == request.target_server_id).first()
    if target_server is None:
        raise HTTPException(status_code=404, detail="Target server not found")

    source_server = None
    if request.source_server_id is not None:
        source_server = db.query(Server).filter(Server.id == request.source_server_id).first()
        if source_server is None:
            raise HTTPException(status_code=404, detail="Source server not found")

    target_snapshot = (
        db.query(EnvironmentSnapshot)
        .filter(
            EnvironmentSnapshot.project_id == project_id,
            EnvironmentSnapshot.server_id == request.target_server_id,
        )
        .order_by(EnvironmentSnapshot.id.desc())
        .first()
    )

    source_snapshot = None
    if request.source_server_id is not None:
        source_snapshot = (
            db.query(EnvironmentSnapshot)
            .filter(
                EnvironmentSnapshot.project_id == project_id,
                EnvironmentSnapshot.server_id == request.source_server_id,
            )
            .order_by(EnvironmentSnapshot.id.desc())
            .first()
        )

    plan = build_mock_config_plan(
        project=project,
        source_server=source_server,
        target_server=target_server,
        source_snapshot=source_snapshot,
        target_snapshot=target_snapshot,
        goal=request.goal,
        allow_command_generation=request.allow_command_generation,
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "source_server_id": request.source_server_id,
        "source_server_name": source_server.name if source_server is not None else None,
        "target_server_id": target_server.id,
        "target_server_name": target_server.name,
        "plan_id": plan["plan_id"],
        "status": plan["status"],
        "goal": plan["goal"],
        "summary": plan["summary"],
        "risk_level": plan["risk_level"],
        "steps": plan["steps"],
        "context": {
            "source_environment_snapshot": format_environment_snapshot(source_snapshot),
            "target_environment_snapshot": format_environment_snapshot(target_snapshot),
        },
    }


@router.post("/projects/{project_id}/ai/analyze-git")
def analyze_project_git(
    project_id: int,
    request: GitAnalyzeRequest | None = None,
    db: Session = Depends(get_db),
):
    request = request or GitAnalyzeRequest()
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    bindings = (
        db.query(ProjectServerMapping, Server)
        .join(Server, ProjectServerMapping.server_id == Server.id)
        .filter(ProjectServerMapping.project_id == project_id)
        .all()
    )
    if not bindings:
        return {
            "success": False,
            "schema_version": "smart-git.v1",
            "project_id": project.id,
            "project_name": project.name,
            "risk": "medium",
            "state": "unknown",
            "summary": "No bound repositories were found for this project.",
            "findings": ["Bind at least one project path before running Git analysis."],
            "reports": {"repositories": []},
            "issues": [],
            "playbook": [],
            "operation_plans": [],
            "blocked_operations": [],
            "next_steps": ["Bind a local or executor-managed repository path."],
            "warnings": [],
        }

    analyses = request.analyses or ["status", "doctor", "map", "sync_plan", "commit_plan"]
    repository_reports = []
    issue_reports = []
    operation_plans = []
    blocked_operations = []
    next_steps = []
    warnings = []
    risk = "low"

    for binding, server in bindings:
        analysis = analyze_repository(binding.project_path, analyses=analyses)
        analysis["server_id"] = server.id
        analysis["server_name"] = server.name
        analysis["project_path"] = binding.project_path
        repository_reports.append(analysis)
        if analysis.get("success"):
            risk = _max_risk(risk, analysis.get("risk"))
        else:
            risk = _max_risk(risk, "medium")
        if analysis.get("issue_report"):
            issue_reports.append(analysis["issue_report"])
        operation_plans.extend(analysis.get("operation_plans") or [])
        blocked_operations.extend(analysis.get("blocked_operations") or [])
        next_steps.extend(analysis.get("next_steps") or [])
        warnings.extend(analysis.get("warnings") or [])
        create_executor_task(
            db=db,
            project_id=project.id,
            server_id=server.id,
            task_type="smart_git_analyze",
            status="completed" if analysis.get("success") else "failed",
            executor_id="local-backend",
            payload={"project_path": binding.project_path, "analyses": analyses},
            result=analysis,
            error_type=analysis.get("error_type"),
            message=analysis.get("message") or f"Smart Git analysis finished for {server.name}",
        )

    issue_report = _merge_issue_reports(issue_reports)
    for issue in issue_report["issues"]:
        risk = _max_risk(risk, issue.get("severity"))

    first_success = next((item for item in repository_reports if item.get("success")), repository_reports[0])
    return {
        "success": all(item.get("success") for item in repository_reports),
        "schema_version": "smart-git.v1",
        "project_id": project.id,
        "project_name": project.name,
        "repo_path": first_success.get("repo_path") or first_success.get("project_path"),
        "branch": first_success.get("branch"),
        "upstream": first_success.get("upstream"),
        "commit": first_success.get("commit"),
        "risk": risk,
        "state": first_success.get("state") or "unknown",
        "summary": issue_report["summary"],
        "findings": [
            f"{len(repository_reports)} bound repositories analyzed.",
            issue_report["summary"],
            "Write operations remain behind executor approval.",
        ],
        "reports": {
            "repositories": repository_reports,
        },
        "issue_report": issue_report,
        "issues": issue_report["issues"],
        "playbook": issue_report["playbook"],
        "operation_plans": operation_plans,
        "blocked_operations": blocked_operations,
        "next_steps": sorted(set(next_steps)),
        "warnings": sorted(set(warnings)),
    }
