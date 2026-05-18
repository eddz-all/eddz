from __future__ import annotations

from datetime import datetime
from pathlib import Path

from projectpilot.models.analysis import GitAnalysis
from projectpilot.models.git_status import GitStatus
from projectpilot.models.recommendation import Recommendation
from projectpilot.utils.paths import timestamped_report_path


def render_markdown_report(
    status: GitStatus,
    analysis: GitAnalysis,
    recommendations: list[Recommendation],
) -> str:
    lines: list[str] = []
    lines.append("# ProjectPilot Git Status Report")
    lines.append("")
    lines.append(f"- Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Repository: `{status.repo_path}`")
    lines.append(f"- Branch: `{status.branch or '(detached HEAD)'}`")
    lines.append(f"- Commit: `{status.commit or 'unknown'}`")
    lines.append(f"- Upstream: `{status.upstream or 'not configured'}`")
    lines.append(f"- Ahead / behind: `+{status.ahead} / -{status.behind}`")
    lines.append(f"- State: `{status.state}`")
    lines.append(f"- Risk: `{analysis.risk.level}`")
    lines.append("")
    lines.append("## Explanation")
    lines.append("")
    lines.append(analysis.explanation)
    lines.append("")
    lines.append("## Risk")
    lines.append("")
    for reason in analysis.risk.reasons:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("## Changed Files")
    lines.append("")
    append_file_group(lines, "Staged", status.staged_files)
    append_file_group(lines, "Unstaged", status.unstaged_files)
    append_file_group(lines, "Untracked", status.untracked_files)
    append_file_group(lines, "Conflicted", status.conflicted_files)
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    for item in recommendations:
        lines.append(f"### {item.title}")
        lines.append("")
        lines.append(f"- Level: `{item.level}`")
        lines.append(f"- Requires confirmation: `{'yes' if item.requires_confirmation else 'no'}`")
        lines.append(f"- Reason: {item.reason}")
        if item.suggested_commands:
            lines.append("- Suggested commands:")
            for command in item.suggested_commands:
                lines.append(f"  - `{command}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def append_file_group(lines: list[str], title: str, files: list[str]) -> None:
    lines.append(f"### {title} ({len(files)})")
    lines.append("")
    if not files:
        lines.append("- None")
    else:
        for path in files:
            lines.append(f"- `{path}`")
    lines.append("")


def save_markdown_report(repo_path: Path, report: str) -> Path:
    path = timestamped_report_path(repo_path, "git-status")
    path.write_text(report, encoding="utf-8")
    return path
