from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectServerMapping, Server
from schemas import ExecuteConfigPlanRequest
from services.execution_service import simulate_config_plan_execution
from services.log_service import create_operation_log


router = APIRouter(tags=["execution"])


@router.post("/projects/{project_id}/servers/{server_id}/execute-config-plan")
def execute_config_plan(
    project_id: int,
    server_id: int,
    request: ExecuteConfigPlanRequest,
    db: Session = Depends(get_db),
):
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="Execution requires user confirmation")

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    binding = (
        db.query(ProjectServerMapping)
        .filter(
            ProjectServerMapping.project_id == project_id,
            ProjectServerMapping.server_id == server_id,
        )
        .first()
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Project-server binding not found")

    if not request.steps:
        raise HTTPException(status_code=400, detail="No config plan steps provided")

    execution = simulate_config_plan_execution(
        request.steps,
        connection_mode=server.connection_mode,
        host=server.host,
        port=server.port,
        username=server.username,
        cwd=binding.project_path,
    )
    risk_order = {"low": 1, "medium": 2, "high": 3}
    highest_risk = max(
        (
            item["safety"]["level"]
            for item in execution["safety_report"]
            if item.get("safety")
        ),
        key=lambda level: risk_order.get(level, 0),
        default="low",
    )

    create_operation_log(
        db=db,
        project_id=project.id,
        server_id=server.id,
        operation_type="execute_config_plan",
        risk_level=highest_risk,
        status=execution["status"],
        summary=f"Executed config plan for {project.name} on {server.name}",
        detail=execution["message"],
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "server_id": server.id,
        "server_name": server.name,
        "project_path": binding.project_path,
        "connection_mode": server.connection_mode,
        "status": execution["status"],
        "message": execution["message"],
        "safety_report": execution["safety_report"],
        "results": execution["results"],
    }
