from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from database import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    operation_type = Column(String, nullable=False)
    risk_level = Column(String, nullable=True)
    status = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    confirmed = Column(Boolean, nullable=False, default=False)
    details = Column(JSON, nullable=True)
    output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
