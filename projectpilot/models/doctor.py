from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DoctorReport:
    repo_path: str
    health: str
    risk: str
    branch: str | None
    upstream: str | None
    is_clean: bool
    ahead: int
    behind: int
    findings: list[str] = field(default_factory=list)
    recommended_next_step: str = ""
    last_audit_operation: str | None = None
    can_add: bool = False
    can_commit: bool = False
    can_push: bool = False
    can_pull: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
