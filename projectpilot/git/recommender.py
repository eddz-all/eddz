from __future__ import annotations

from projectpilot.models.analysis import GitAnalysis
from projectpilot.models.git_status import GitStatus
from projectpilot.models.recommendation import Recommendation


def build_recommendations(status: GitStatus, analysis: GitAnalysis) -> list[Recommendation]:
    recommendations: list[Recommendation] = []

    if status.state != "normal":
        recommendations.append(
            Recommendation(
                level="high",
                title=f"Finish the current {status.state} operation",
                reason="Git is in an intermediate state, so normal pull or push operations are unsafe.",
                suggested_commands=["git status", "git diff"],
                requires_confirmation=False,
            )
        )
        return recommendations

    if status.conflicted_files:
        recommendations.append(
            Recommendation(
                level="high",
                title="Resolve conflicts first",
                reason="Conflicted files block safe commit, pull, and push workflows.",
                suggested_commands=["git status", "git diff --check"],
                requires_confirmation=False,
            )
        )
        return recommendations

    if not analysis.has_upstream:
        recommendations.append(
            Recommendation(
                level="medium",
                title="Configure an upstream branch",
                reason="Without upstream tracking, ProjectPilot cannot safely judge pull and push state.",
                suggested_commands=["git branch -vv", "git push -u origin HEAD"],
                requires_confirmation=True,
            )
        )

    if analysis.is_diverged:
        recommendations.append(
            Recommendation(
                level="high",
                title="Inspect diverged history before integrating",
                reason="Both local and upstream branches have new commits. A simple push is blocked and pull may require conflict handling.",
                suggested_commands=[
                    "git fetch",
                    f"git log --oneline --graph --decorate --left-right {status.branch or 'HEAD'}...{status.upstream or '@{upstream}'}",
                ],
                requires_confirmation=False,
            )
        )
        return recommendations

    if status.unstaged_files or status.untracked_files:
        recommendations.append(
            Recommendation(
                level="medium",
                title="Review working tree changes",
                reason="There are unstaged or untracked files. Review them before pull, commit, or add-all operations.",
                suggested_commands=["git diff", "git status --short"],
                requires_confirmation=False,
            )
        )

    if status.staged_files:
        recommendations.append(
            Recommendation(
                level="medium",
                title="Commit staged changes when ready",
                reason="Staged files are ready for commit. Confirm the diff and write a clear commit message.",
                suggested_commands=["git diff --cached", "git commit -m \"<message>\""],
                requires_confirmation=True,
            )
        )

    if analysis.can_pull:
        recommendations.append(
            Recommendation(
                level="low",
                title="Pull upstream changes",
                reason="The working tree is clean and the local branch is behind upstream.",
                suggested_commands=["git pull --ff-only"],
                requires_confirmation=True,
            )
        )
    elif analysis.is_behind and analysis.is_dirty:
        recommendations.append(
            Recommendation(
                level="medium",
                title="Commit or stash before pulling",
                reason="The local branch is behind upstream, but the working tree is not clean.",
                suggested_commands=["git diff", "git stash push -u", "git pull --ff-only"],
                requires_confirmation=True,
            )
        )

    if analysis.can_push:
        recommendations.append(
            Recommendation(
                level="low",
                title="Push local commits",
                reason="The branch is ahead of upstream and no divergence was detected.",
                suggested_commands=["git push"],
                requires_confirmation=True,
            )
        )

    if not recommendations:
        recommendations.append(
            Recommendation(
                level="low",
                title="No action needed",
                reason="The working tree is clean and the branch appears aligned with upstream.",
                suggested_commands=["git status"],
                requires_confirmation=False,
            )
        )

    return recommendations
