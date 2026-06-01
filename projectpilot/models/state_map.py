from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class StateMapFile:
    path: str
    status: str
    area: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LocalCommitSummary:
    ahead: int
    commits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RemoteSummary:
    has_upstream: bool
    upstream: str | None
    behind: int
    diverged: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GitStateMap:
    repo_path: str
    branch: str | None
    upstream: str | None
    commit: str | None
    state: str
    risk: str
    working_tree: list[StateMapFile] = field(default_factory=list)
    staged: list[StateMapFile] = field(default_factory=list)
    untracked: list[StateMapFile] = field(default_factory=list)
    conflicted: list[StateMapFile] = field(default_factory=list)
    local_commits: LocalCommitSummary | None = None
    remote: RemoteSummary | None = None
    next_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "branch": self.branch,
            "upstream": self.upstream,
            "commit": self.commit,
            "state": self.state,
            "risk": self.risk,
            "working_tree": [item.to_dict() for item in self.working_tree],
            "staged": [item.to_dict() for item in self.staged],
            "untracked": [item.to_dict() for item in self.untracked],
            "conflicted": [item.to_dict() for item in self.conflicted],
            "local_commits": self.local_commits.to_dict() if self.local_commits else None,
            "remote": self.remote.to_dict() if self.remote else None,
            "next_steps": list(self.next_steps),
            "warnings": list(self.warnings),
        }

