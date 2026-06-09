from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class ProjectServerMapping(Base):
    __tablename__ = "project_server_mappings"
    __table_args__ = (UniqueConstraint("project_id", "server_id", name="uq_project_server"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    project_path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
