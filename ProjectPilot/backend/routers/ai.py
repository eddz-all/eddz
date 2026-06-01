from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import get_ai_settings
from database import get_db
from models import EnvironmentSnapshot, Project, ProjectServerMapping, Server
from schemas import AIAnalyzeRequest, ConfigPlanRequest, SmartGitAnalyzeRequest
from services.eddz_bridge import bridge_analyze_repository, integration_runtime
from services.ai_service import analyze_environment, generate_config_plan
from services.formatters import format_environment_snapshot
from services.log_service import create_operation_log, format_operation_log


router = APIRouter(tags=["ai"])


def resolve_smart_git_project_path(project: Project, bindings):
    project_path = Path(project.path).expanduser()
    if project_path.exists():
        return str(project_path), "project.path"

    for binding, server in bindings:
        binding_path = Path(binding.project_path).expanduser()
        if server.connection_mode == "local" and binding_path.exists():
            return str(binding_path), "local_binding"

    return str(project_path), "project.path_missing"


@router.get("/ai/settings")
def get_ai_runtime_settings():
    settings = get_ai_settings()

    return {
        "provider": settings.provider,
        "model": settings.model,
        "base_url": settings.base_url,
        "has_api_key": bool(settings.api_key),
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

    analysis = analyze_environment(
        project=project,
        question=request.question,
        focus=request.focus,
        server_snapshots=server_snapshots,
    )

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

    plan = generate_config_plan(
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
    request: SmartGitAnalyzeRequest,
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

    project_path, path_source = resolve_smart_git_project_path(project, bindings)
    if bridge_analyze_repository is None:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "eddz smart_git integration is not available",
                "runtime": integration_runtime(),
            },
        )

    analysis = bridge_analyze_repository(project_path, analyses=request.analyses)
    status = "completed" if analysis.get("success") else "failed"
    log = create_operation_log(
        db=db,
        project_id=project.id,
        operation_type="analyze_project_git",
        risk_level=analysis.get("risk", "low") if analysis.get("success") else "medium",
        status=status,
        summary="使用 eddz smart_git 分析项目仓库状态",
        confirmed=False,
        details={
            "requested_analyses": request.analyses,
            "project_path": project_path,
            "path_source": path_source,
            "integration_runtime": integration_runtime(),
            "analysis": analysis,
        },
        error_message=None if analysis.get("success") else analysis.get("message"),
    )

    response = {
        "project_id": project.id,
        "project_name": project.name,
        "project_path": project_path,
        "path_source": path_source,
        "requested_analyses": request.analyses,
        "integration_runtime": integration_runtime(),
        "operation_log": format_operation_log(log),
        "analysis": analysis,
    }

    if not analysis.get("success"):
        raise HTTPException(status_code=400, detail=response)

    return response
