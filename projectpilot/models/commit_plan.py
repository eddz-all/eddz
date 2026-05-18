from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class CommitPlanItem:
    path: str
    status: str
    category: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CommitPlan:
    repo_path: str
    branch: str | None
    summary: str
    suggested_message: str | None
    include: list[CommitPlanItem] = field(default_factory=list)
    review: list[CommitPlanItem] = field(default_factory=list)
    exclude: list[CommitPlanItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["include"] = [item.to_dict() for item in self.include]
        data["review"] = [item.to_dict() for item in self.review]
        data["exclude"] = [item.to_dict() for item in self.exclude]
        return data
