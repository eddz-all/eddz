from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class BlockedOperation:
    operation: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GitSyncPlan:
    repo_path: str
    branch: str | None
    upstream: str | None
    commit: str | None
    risk: str
    sync_state: str
    working_tree_state: str
    ahead: int
    behind: int
    can_push: bool
    can_pull_ff_only: bool
    recommended_action: str
    explanation: str
    operation_plans: list[dict] = field(default_factory=list)
    blocked_operations: list[BlockedOperation] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "branch": self.branch,
            "upstream": self.upstream,
            "commit": self.commit,
            "risk": self.risk,
            "sync_state": self.sync_state,
            "working_tree_state": self.working_tree_state,
            "ahead": self.ahead,
            "behind": self.behind,
            "can_push": self.can_push,
            "can_pull_ff_only": self.can_pull_ff_only,
            "recommended_action": self.recommended_action,
            "explanation": self.explanation,
            "operation_plans": list(self.operation_plans),
            "blocked_operations": [item.to_dict() for item in self.blocked_operations],
            "next_steps": list(self.next_steps),
            "warnings": list(self.warnings),
        }

