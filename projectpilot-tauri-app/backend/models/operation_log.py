from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    operation_type = Column(String, nullable=False)
    risk_level = Column(String, nullable=False, default="low")
    status = Column(String, nullable=False, default="completed")
    summary = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
