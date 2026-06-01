from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from database import Base


class ExecutorTask(Base):
    __tablename__ = "executor_tasks"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    task_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    executor_id = Column(String, nullable=True)
    error_type = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
