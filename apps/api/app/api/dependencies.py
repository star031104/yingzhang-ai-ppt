from app.db.models import Project, SlideSpecRecord
from fastapi import HTTPException
from sqlalchemy.orm import Session


def project_or_404(project_id: str, db: Session) -> Project:
    from app.security.accounts import authorize_project
    authorize_project(db, project_id)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def project_slide_or_404(project_id: str, slide_id: str, db: Session) -> SlideSpecRecord:
    project_or_404(project_id, db)
    slide = db.get(SlideSpecRecord, slide_id)
    if slide is None or slide.project_id != project_id:
        raise HTTPException(404, "Slide not found")
    return slide
