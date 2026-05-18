from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from projectpilot.git.analyzer import analyze_status
from projectpilot.git.executor import get_diff, get_log, run_fetch
from projectpilot.git.inspector import NotGitRepositoryError, inspect_repository
from projectpilot.git.parser import parse_ahead_behind
from projectpilot.git.recommender import build_recommendations
from projectpilot.git.reporter import render_markdown_report


class GitIntelligenceTests(unittest.TestCase):
    def test_non_git_directory_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(NotGitRepositoryError):
                inspect_repository(Path(temp_dir))

    def test_clean_repository_without_upstream(self) -> None:
        with git_repo() as repo:
            status = inspect_repository(repo)
            analysis = analyze_status(status)
            recommendations = build_recommendations(status, analysis)

            self.assertTrue(status.is_clean)
            self.assertEqual(status.branch, "main")
            self.assertFalse(analysis.has_upstream)
            self.assertEqual(analysis.risk.level, "medium")
            self.assertTrue(any("upstream" in item.title.lower() for item in recommendations))

    def test_dirty_repository_is_not_clean(self) -> None:
        with git_repo() as repo:
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (repo / "new.txt").write_text("new\n", encoding="utf-8")

            status = inspect_repository(repo)
            analysis = analyze_status(status)

            self.assertFalse(status.is_clean)
            self.assertEqual(status.unstaged_files, ["tracked.txt"])
            self.assertEqual(status.untracked_files, ["new.txt"])
            self.assertTrue(analysis.needs_commit)
            self.assertEqual(analysis.risk.level, "medium")

    def test_report_contains_recommendations(self) -> None:
        with git_repo() as repo:
            status = inspect_repository(repo)
            analysis = analyze_status(status)
            recommendations = build_recommendations(status, analysis)
            report = render_markdown_report(status, analysis, recommendations)

            self.assertIn("# ProjectPilot Git Status Report", report)
            self.assertIn("## Recommendations", report)
            self.assertIn("Configure an upstream branch", report)

    def test_parse_ahead_behind(self) -> None:
        self.assertEqual(parse_ahead_behind("+3 -2"), (3, 2))

    def test_non_ascii_paths_are_readable(self) -> None:
        with git_repo() as repo:
            (repo / "智能Git.md").write_text("notes\n", encoding="utf-8")

            status = inspect_repository(repo)

            self.assertEqual(status.untracked_files, ["智能Git.md"])

    def test_diff_and_log_commands(self) -> None:
        with git_repo() as repo:
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")

            diff = get_diff(repo)
            log = get_log(repo, limit=3)

            self.assertIn("tracked.txt", diff.stdout)
            self.assertIn("initial", log.stdout)

    def test_fetch_requires_remote(self) -> None:
        with git_repo() as repo:
            with self.assertRaisesRegex(RuntimeError, "No Git remotes"):
                run_fetch(repo)

    def test_fetch_with_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = root / "remote.git"
            repo = root / "repo"
            remote.mkdir()
            repo.mkdir()

            run(["git", "init", "--bare"], remote)
            init_repo(repo)
            run(["git", "remote", "add", "origin", str(remote)], repo)

            result, status = run_fetch(repo, remote="origin")

            self.assertEqual(result.returncode, 0)
            self.assertIn("origin", status.remotes)


class git_repo:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        repo = Path(self.temp_dir.name)
        init_repo(repo)
        self.repo = repo
        return repo

    def __exit__(self, exc_type, exc, tb) -> None:
        self.temp_dir.cleanup()


def init_repo(repo: Path) -> None:
    run(["git", "init", "-b", "main"], repo)
    run(["git", "config", "user.name", "ProjectPilot Test"], repo)
    run(["git", "config", "user.email", "projectpilot@example.test"], repo)
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    run(["git", "add", "tracked.txt"], repo)
    run(["git", "commit", "-m", "initial"], repo)


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


if __name__ == "__main__":
    unittest.main()
