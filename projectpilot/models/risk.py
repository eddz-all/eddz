from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RiskAssessment:
    level: str
    reasons: list[str] = field(default_factory=list)
    blocked_operations: list[str] = field(default_factory=list)
    allowed_operations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
