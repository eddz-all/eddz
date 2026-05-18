from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Recommendation:
    level: str
    title: str
    reason: str
    suggested_commands: list[str] = field(default_factory=list)
    requires_confirmation: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
