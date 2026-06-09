from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import get_ai_settings
from database import get_db
from models import EnvironmentSnapshot, GitStatus, Project, ProjectServerMapping, Server
from schemas import (
    AIActionPlanRequest,
    AIAnalyzeRequest,
    ConfigPlanRequest,
    ConfigPlanStepExecute,
    SmartGitAnalyzeRequest,
)
from services.eddz_bridge import bridge_analyze_repository, integration_runtime
from services.ai_service import analyze_environment, generate_action_plan, generate_config_plan
from services.executor_task_service import create_executor_task, format_executor_task
from services.execution_service import execute_config_plan_steps, inspect_config_plan_steps
from services.formatters import format_environment_snapshot, format_git_status
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


def latest_environment_snapshot(db: Session, project_id: int, server_id: int):
    return (
        db.query(EnvironmentSnapshot)
        .filter(
            EnvironmentSnapshot.project_id == project_id,
            EnvironmentSnapshot.server_id == server_id,
        )
        .order_by(EnvironmentSnapshot.id.desc())
        .first()
    )


def latest_git_status(db: Session, project_id: int, server_id: int):
    return (
        db.query(GitStatus)
        .filter(
            GitStatus.project_id == project_id,
            GitStatus.server_id == server_id,
        )
        .order_by(GitStatus.id.desc())
        .first()
    )


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


@router.post("/projects/{project_id}/ai/plan-action")
def plan_and_optionally_execute_action(
    project_id: int,
    request: AIActionPlanRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    target_server = db.query(Server).filter(Server.id == request.target_server_id).first()
    if target_server is None:
        raise HTTPException(status_code=404, detail="Target server not found")

    target_binding = (
        db.query(ProjectServerMapping)
        .filter(
            ProjectServerMapping.project_id == project_id,
            ProjectServerMapping.server_id == request.target_server_id,
        )
        .first()
    )
    if target_binding is None:
        raise HTTPException(status_code=404, detail="Target project-server binding not found")

    source_server = None
    source_binding = None
    if request.source_server_id is not None:
        source_server = db.query(Server).filter(Server.id == request.source_server_id).first()
        if source_server is None:
            raise HTTPException(status_code=404, detail="Source server not found")
        source_binding = (
            db.query(ProjectServerMapping)
            .filter(
                ProjectServerMapping.project_id == project_id,
                ProjectServerMapping.server_id == request.source_server_id,
            )
            .first()
        )

    target_snapshot = latest_environment_snapshot(db, project_id, target_server.id)
    source_snapshot = (
        latest_environment_snapshot(db, project_id, source_server.id)
        if source_server is not None
        else None
    )
    target_git = latest_git_status(db, project_id, target_server.id)
    source_git = (
        latest_git_status(db, project_id, source_server.id)
        if source_server is not None
        else None
    )

    plan = generate_action_plan(
        project=project,
        target_server=target_server,
        target_snapshot=target_snapshot,
        target_git_status=target_git,
        goal=request.goal,
        allow_command_generation=request.allow_command_generation,
        source_server=source_server,
        source_snapshot=source_snapshot,
        source_git_status=source_git,
    )

    generation_log = create_operation_log(
        db=db,
        project_id=project.id,
        server_id=target_server.id,
        operation_type="ai_plan_action",
        risk_level=plan.get("risk_level", "medium"),
        status="completed",
        summary="根据自然语言需求生成主动执行计划",
        confirmed=request.confirmed,
        details={
            "goal": request.goal,
            "auto_execute": request.auto_execute,
            "allow_command_generation": request.allow_command_generation,
            "target_server_id": target_server.id,
            "source_server_id": source_server.id if source_server is not None else None,
            "plan": plan,
        },
    )

    response = {
        "project_id": project.id,
        "project_name": project.name,
        "goal": request.goal,
        "target_server": {
            "id": target_server.id,
            "name": target_server.name,
            "connection_mode": target_server.connection_mode,
            "project_path": target_binding.project_path,
        },
        "source_server": {
            "id": source_server.id,
            "name": source_server.name,
            "connection_mode": source_server.connection_mode,
            "project_path": source_binding.project_path if source_binding is not None else None,
        }
        if source_server is not None
        else None,
        "plan": plan,
        "context": {
            "target_environment_snapshot": format_environment_snapshot(target_snapshot),
            "source_environment_snapshot": format_environment_snapshot(source_snapshot),
            "target_git_status": format_git_status(target_git),
            "source_git_status": format_git_status(source_git),
        },
        "operation_log": format_operation_log(generation_log),
    }

    if not request.auto_execute:
        response["status"] = "preview"
        response["message"] = "AI action plan generated. Review before execution."
        return response

    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail={
                **response,
                "status": "confirmation_required",
                "message": "Execution requires user confirmation.",
            },
        )

    plan_steps = [
        ConfigPlanStepExecute(
            order=int(step.get("order") or index + 1),
            title=step.get("title"),
            command=step.get("command"),
            risk_level=step.get("risk_level"),
        )
        for index, step in enumerate(plan.get("steps", []))
    ]

    executable_steps = [step for step in plan_steps if step.command]
    if not executable_steps:
        response["status"] = "no_executable_steps"
        response["message"] = "AI plan generated, but no executable commands were produced."
        return response

    safety_report = inspect_config_plan_steps(executable_steps)
    response["safety_report"] = safety_report

    if target_server.connection_mode == "executor":
        blocked_items = [item for item in safety_report if item["safety"]["level"] == "blocked"]
        if blocked_items:
            blocked_log = create_operation_log(
                db=db,
                project_id=project.id,
                server_id=target_server.id,
                operation_type="ai_plan_action_execute",
                risk_level="high",
                status="blocked",
                summary="AI 计划包含危险命令，未创建 Executor 任务",
                confirmed=request.confirmed,
                details={
                    "goal": request.goal,
                    "safety_report": safety_report,
                    "plan": plan,
                },
                error_message="Blocked steps detected",
            )
            response["status"] = "blocked"
            response["message"] = "Blocked steps detected. No executor tasks were created."
            response["tasks"] = []
            response["execution_log"] = format_operation_log(blocked_log)
            return response

        queued_tasks = []
        for step in executable_steps:
            queued_tasks.append(
                create_executor_task(
                    db=db,
                    project_id=project.id,
                    server_id=target_server.id,
                    task_type="run_local_script",
                    payload={
                        "project_path": target_binding.project_path,
                        "script": step.command,
                        "interpreter": "bash",
                        "approved": True,
                        "risk_level": step.risk_level or "medium",
                        "title": step.title,
                        "order": step.order,
                        "goal": request.goal,
                    },
                    executor_id=target_server.name,
                    summary=f"等待 Executor 执行 AI 生成步骤 #{step.order}",
                    risk_level=step.risk_level or "medium",
                    confirmed=request.confirmed,
                )
            )

        dispatch_log = create_operation_log(
            db=db,
            project_id=project.id,
            server_id=target_server.id,
            operation_type="ai_plan_action_execute",
            risk_level=plan.get("risk_level", "medium"),
            status="queued",
            summary="AI 主动需求已转换为 Executor 执行任务",
            confirmed=request.confirmed,
            details={
                "goal": request.goal,
                "task_ids": [task.id for task in queued_tasks],
                "safety_report": safety_report,
                "plan": plan,
            },
        )
        response["status"] = "queued"
        response["message"] = "AI action plan queued for executor execution."
        response["tasks"] = [format_executor_task(task) for task in queued_tasks]
        response["execution_log"] = format_operation_log(dispatch_log)
        return response

    results = execute_config_plan_steps(target_server, target_binding.project_path, executable_steps)
    failed_results = [result for result in results if result["status"] != "success"]
    blocked_results = [result for result in results if result["status"] == "blocked"]
    status = "blocked" if blocked_results else "failed" if failed_results else "completed"
    execution_log = create_operation_log(
        db=db,
        project_id=project.id,
        server_id=target_server.id,
        operation_type="ai_plan_action_execute",
        risk_level=plan.get("risk_level", "medium"),
        status=status,
        summary="执行 AI 主动生成的计划",
        confirmed=request.confirmed,
        details={
            "goal": request.goal,
            "safety_report": safety_report,
            "plan": plan,
        },
        output=str(results),
        error_message=None if not failed_results else "Some AI-generated steps failed or were blocked",
    )
    response["status"] = status
    response["message"] = "AI action plan executed."
    response["results"] = results
    response["execution_log"] = format_operation_log(execution_log)
    return response
