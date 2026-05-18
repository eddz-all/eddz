from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    operation: str
    risk: str
    command: list[str]
    success: bool
    repo_path: str
    branch: str | None
    before_commit: str | None
    after_commit: str | None
    before_clean: bool
    after_clean: bool
    stdout_summary: str
    stderr_summary: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        return cls(
            timestamp=str(data.get("timestamp", "")),
            operation=str(data.get("operation", "")),
            risk=str(data.get("risk", "")),
            command=list(data.get("command", [])),
            success=bool(data.get("success", False)),
            repo_path=str(data.get("repo_path", "")),
            branch=data.get("branch"),
            before_commit=data.get("before_commit"),
            after_commit=data.get("after_commit"),
            before_clean=bool(data.get("before_clean", False)),
            after_clean=bool(data.get("after_clean", False)),
            stdout_summary=str(data.get("stdout_summary", "")),
            stderr_summary=str(data.get("stderr_summary", "")),
        )
