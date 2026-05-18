from __future__ import annotations

from dataclasses import asdict, dataclass, field

from projectpilot.models.git_status import GitStatus


@dataclass(frozen=True)
class OperationPlan:
    operation: str
    repo_path: str
    risk: str
    allowed: bool
    requires_apply: bool
    command: list[str] = field(default_factory=list)
    reason: str = ""
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    planned_paths: list[str] = field(default_factory=list)
    review_paths: list[str] = field(default_factory=list)
    excluded_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OperationResult:
    operation: str
    success: bool
    stdout: str
    stderr: str
    before_status: GitStatus
    after_status: GitStatus
    plan: OperationPlan

    def to_dict(self) -> dict:
        data = asdict(self)
        data["before_status"] = self.before_status.to_dict()
        data["after_status"] = self.after_status.to_dict()
        data["plan"] = self.plan.to_dict()
        return data
