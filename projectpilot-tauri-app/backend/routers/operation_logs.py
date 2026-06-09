from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import OperationLog, Project, Server
from services.log_service import format_operation_log


router = APIRouter(tags=["operation-logs"])


@router.get("/operation-logs")
def get_operation_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = db.query(OperationLog).order_by(OperationLog.id.desc()).limit(limit).all()
    return [format_operation_log(log) for log in logs]


@router.get("/projects/{project_id}/operation-logs")
def get_project_operation_logs(
    project_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    logs = (
        db.query(OperationLog)
        .filter(OperationLog.project_id == project_id)
        .order_by(OperationLog.id.desc())
        .limit(limit)
        .all()
    )
    return [format_operation_log(log) for log in logs]


@router.get("/servers/{server_id}/operation-logs")
def get_server_operation_logs(
    server_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    server = db.query(Server).filter(Server.id == server_id).first()
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")

    logs = (
        db.query(OperationLog)
        .filter(OperationLog.server_id == server_id)
        .order_by(OperationLog.id.desc())
        .limit(limit)
        .all()
    )
    return [format_operation_log(log) for log in logs]
