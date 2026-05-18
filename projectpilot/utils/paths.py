from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_report_dir(repo_path: Path) -> Path:
    report_dir = repo_path / ".projectpilot" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def timestamped_report_path(repo_path: Path, prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ensure_report_dir(repo_path) / f"{prefix}-{timestamp}.md"
