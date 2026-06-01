from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Project
from schemas import ProjectCreate


router = APIRouter(tags=["projects"])


@router.post("/projects")
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    existing_project = db.query(Project).filter(Project.path == project.path).first()

    if existing_project is not None:
        raise HTTPException(status_code=400, detail="Project path already exists")

    new_project = Project(
        name=project.name,
        path=project.path,
        description=project.description,
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return {
        "id": new_project.id,
        "name": new_project.name,
        "path": new_project.path,
        "description": new_project.description,
    }


@router.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()

    return [
        {
            "id": project.id,
            "name": project.name,
            "path": project.path,
            "description": project.description,
            "created_at": project.created_at,
        }
        for project in projects
    ]


@router.get("/projects/{project_id}")
def get_project_by_id(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "id": project.id,
        "name": project.name,
        "path": project.path,
        "description": project.description,
        "created_at": project.created_at,
    }


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()

    return {"message": "Project deleted successfully"}

