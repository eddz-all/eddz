from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project, ProjectServerMapping, Server
from schemas import ExecuteConfigPlanRequest
from services.executor_task_service import create_executor_task, format_executor_task
from services.execution_service import execute_config_plan_steps, inspect_config_plan_steps
from services.log_service import create_operation_log, format_operation_log


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

    safety_report = inspect_config_plan_steps(request.steps)
    if server.connection_mode == "executor":
        blocked_items = [item for item in safety_report if item["safety"]["level"] == "blocked"]
        if blocked_items:
            log = create_operation_log(
                db=db,
                project_id=project.id,
                server_id=server.id,
                operation_type="execute_config_plan",
                risk_level="high",
                status="blocked",
                summary="配置计划存在危险命令，未创建 Executor 任务",
                confirmed=request.confirmed,
                details={
                    "steps": [step.model_dump() for step in request.steps],
                    "safety_report": safety_report,
                    "connection_mode": server.connection_mode,
                },
                error_message="Blocked steps detected",
            )
            return {
                "project_id": project.id,
                "project_name": project.name,
                "server_id": server.id,
                "server_name": server.name,
                "project_path": binding.project_path,
                "connection_mode": server.connection_mode,
                "status": "blocked",
                "message": "Blocked steps detected. No executor tasks were created.",
                "safety_report": safety_report,
                "tasks": [],
                "operation_log": format_operation_log(log),
            }

        queued_tasks = []
        for step in request.steps:
            if not step.command:
                continue
            queued_tasks.append(
                create_executor_task(
                    db=db,
                    project_id=project.id,
                    server_id=server.id,
                    task_type="run_local_script",
                    payload={
                        "project_path": binding.project_path,
                        "script": step.command,
                        "interpreter": "bash",
                        "approved": True,
                        "risk_level": step.risk_level or "medium",
                        "title": step.title,
                        "order": step.order,
                    },
                    executor_id=server.name,
                    summary=f"等待 Executor 执行配置步骤 #{step.order}",
                    risk_level=step.risk_level or "medium",
                    confirmed=request.confirmed,
                )
            )

        if not queued_tasks:
            raise HTTPException(status_code=400, detail="No executable commands were provided")

        highest_risk = "low"
        risk_order = {"low": 1, "medium": 2, "high": 3}
        for step in request.steps:
            level = step.risk_level or "low"
            if risk_order.get(level, 1) > risk_order[highest_risk]:
                highest_risk = level

        log = create_operation_log(
            db=db,
            project_id=project.id,
            server_id=server.id,
            operation_type="execute_config_plan",
            risk_level=highest_risk,
            status="queued",
            summary="已创建 Executor 配置执行任务",
            confirmed=request.confirmed,
            details={
                "steps": [step.model_dump() for step in request.steps],
                "safety_report": safety_report,
                "connection_mode": server.connection_mode,
                "task_ids": [task.id for task in queued_tasks],
            },
        )
        return {
            "project_id": project.id,
            "project_name": project.name,
            "server_id": server.id,
            "server_name": server.name,
            "project_path": binding.project_path,
            "connection_mode": server.connection_mode,
            "status": "queued",
            "message": "Config plan queued for executor execution.",
            "safety_report": safety_report,
            "tasks": [format_executor_task(task) for task in queued_tasks],
            "operation_log": format_operation_log(log),
        }

    results = execute_config_plan_steps(server, binding.project_path, request.steps)
    failed_results = [result for result in results if result["status"] != "success"]
    blocked_results = [result for result in results if result["status"] == "blocked"]
    status = "blocked" if blocked_results else "failed" if failed_results else "completed"
    risk_order = {"low": 1, "medium": 2, "high": 3}
    risk_level = "low"
    for step in request.steps:
        if step.risk_level in risk_order and risk_order[step.risk_level] > risk_order[risk_level]:
            risk_level = step.risk_level

    log = create_operation_log(
        db=db,
        project_id=project.id,
        server_id=server.id,
        operation_type="execute_config_plan",
        risk_level=risk_level,
        status=status,
        summary="执行配置计划（安全检查 + 模拟执行）",
        confirmed=request.confirmed,
        details={
            "steps": [step.model_dump() for step in request.steps],
            "safety_report": safety_report,
            "connection_mode": server.connection_mode,
        },
        output=str(results),
        error_message=None if not failed_results else "Some steps failed or were blocked",
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "server_id": server.id,
        "server_name": server.name,
        "project_path": binding.project_path,
        "connection_mode": server.connection_mode,
        "status": status,
        "message": "Config plan execution finished with safety checks.",
        "safety_report": safety_report,
        "results": results,
        "operation_log": format_operation_log(log),
    }
