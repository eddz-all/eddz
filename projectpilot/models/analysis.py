from __future__ import annotations

from dataclasses import asdict, dataclass, field

from projectpilot.models.risk import RiskAssessment


@dataclass(frozen=True)
class GitAnalysis:
    is_dirty: bool
    has_upstream: bool
    is_ahead: bool
    is_behind: bool
    is_diverged: bool
    needs_commit: bool
    can_pull: bool
    can_push: bool
    risk: RiskAssessment
    explanation: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["risk"] = self.risk.to_dict()
        return data
