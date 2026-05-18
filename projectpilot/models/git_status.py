from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GitFileChange:
    path: str
    index_status: str = "."
    worktree_status: str = "."

    @property
    def is_staged(self) -> bool:
        return self.index_status not in {".", " "}

    @property
    def is_unstaged(self) -> bool:
        return self.worktree_status not in {".", " "}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GitStatus:
    repo_path: Path
    branch: str | None
    upstream: str | None
    commit: str | None
    is_clean: bool
    ahead: int = 0
    behind: int = 0
    staged_files: list[str] = field(default_factory=list)
    unstaged_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    conflicted_files: list[str] = field(default_factory=list)
    changed_files: list[GitFileChange] = field(default_factory=list)
    remotes: dict[str, list[str]] = field(default_factory=dict)
    state: str = "normal"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["repo_path"] = str(self.repo_path)
        data["changed_files"] = [item.to_dict() for item in self.changed_files]
        return data
