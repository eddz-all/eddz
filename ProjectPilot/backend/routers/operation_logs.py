from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import OperationLog
from services.log_service import format_operation_log


router = APIRouter(tags=["operation-logs"])


@router.get("/operation-logs")
def get_operation_logs(db: Session = Depends(get_db)):
    logs = db.query(OperationLog).order_by(OperationLog.id.desc()).all()
    return [format_operation_log(log) for log in logs]


@router.get("/projects/{project_id}/operation-logs")
def get_project_operation_logs(project_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(OperationLog)
        .filter(OperationLog.project_id == project_id)
        .order_by(OperationLog.id.desc())
        .all()
    )
    return [format_operation_log(log) for log in logs]


@router.get("/servers/{server_id}/operation-logs")
def get_server_operation_logs(server_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(OperationLog)
        .filter(OperationLog.server_id == server_id)
        .order_by(OperationLog.id.desc())
        .all()
    )
    return [format_operation_log(log) for log in logs]
