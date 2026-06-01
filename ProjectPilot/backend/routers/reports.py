from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project
from schemas import ProjectReportRequest
from services.report_service import generate_project_report


router = APIRouter(tags=["reports"])


@router.post("/reports/project")
def create_project_report(
    request: ProjectReportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    content = generate_project_report(
        project=project,
        db=db,
        include_ai_analysis=request.include_ai_analysis,
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "format": "markdown",
        "content": content,
    }
