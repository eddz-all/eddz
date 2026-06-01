from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class GitStatus(Base):
    __tablename__ = "git_statuses"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    branch = Column(String, nullable=False)
    remote_url = Column(String, nullable=True)
    ahead = Column(Integer, nullable=False, default=0)
    behind = Column(Integer, nullable=False, default=0)
    has_uncommitted_changes = Column(Boolean, nullable=False, default=False)
    last_commit = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
