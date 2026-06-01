from models import OperationLog


def create_operation_log(
    db,
    operation_type: str,
    status: str,
    project_id: int | None = None,
    server_id: int | None = None,
    risk_level: str | None = None,
    summary: str | None = None,
    confirmed: bool = False,
    details: dict | None = None,
    output: str | None = None,
    error_message: str | None = None,
):
    log = OperationLog(
        project_id=project_id,
        server_id=server_id,
        operation_type=operation_type,
        risk_level=risk_level,
        status=status,
        summary=summary,
        confirmed=confirmed,
        details=details,
        output=output,
        error_message=error_message,
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
        "confirmed": log.confirmed,
        "details": log.details,
        "output": log.output,
        "error_message": log.error_message,
        "created_at": log.created_at,
    }
