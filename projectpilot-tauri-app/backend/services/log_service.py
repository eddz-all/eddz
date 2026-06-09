from models import OperationLog


def create_operation_log(
    db,
    operation_type: str,
    summary: str,
    project_id: int | None = None,
    server_id: int | None = None,
    risk_level: str = "low",
    status: str = "completed",
    detail: str | None = None,
):
    log = OperationLog(
        project_id=project_id,
        server_id=server_id,
        operation_type=operation_type,
        risk_level=risk_level,
        status=status,
        summary=summary,
        detail=detail,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def format_operation_log(log: OperationLog):
    return {
        "id": log.id,
        "project_id": log.project_id,
        "server_id": log.server_id,
        "operation_type": log.operation_type,
        "risk_level": log.risk_level,
        "status": log.status,
        "summary": log.summary,
        "detail": log.detail,
        "created_at": log.created_at,
    }
