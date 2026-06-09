from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import EnvironmentSnapshot, Project, ProjectServerMapping, Server
from schemas import AIAnalyzeRequest, ConfigPlanRequest
from services.ai_service import build_mock_config_plan, build_mock_environment_analysis
from services.formatters import format_environment_snapshot


router = APIRouter(tags=["ai"])


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
