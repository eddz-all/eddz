from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from database import Base


class ExecutorTask(Base):
    __tablename__ = "executor_tasks"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String, nullable=False, unique=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    task_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    priority = Column(Integer, nullable=False, default=100)
    approval_status = Column(String, nullable=False, default="not_required")
    executor_id = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error_type = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
