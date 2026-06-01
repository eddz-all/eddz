from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from projectpilot.integration.member_b import detect_local_environment, detect_local_git_status


class MemberBIntegrationTests(unittest.TestCase):
    def test_local_git_status_reports_non_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = detect_local_git_status(temp_dir)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "not_git_repository")

    def test_local_git_status_reports_clean_repository(self) -> None:
        with git_repo() as repo:
            result = detect_local_git_status(str(repo))

        self.assertTrue(result["success"])
        self.assertEqual(result["branch"], "main")
        self.assertEqual(result["ahead"], 0)
        self.assertEqual(result["behind"], 0)
        self.assertFalse(result["has_uncommitted_changes"])
        self.assertTrue(result["is_clean"])
        self.assertTrue(result["last_commit"].endswith(" initial"))
        self.assertIn("git_status", result["raw_data"])

    def test_local_git_status_reports_dirty_repository(self) -> None:
        with git_repo() as repo:
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (repo / "draft.txt").write_text("draft\n", encoding="utf-8")

            result = detect_local_git_status(str(repo))

        self.assertTrue(result["success"])
        self.assertTrue(result["has_uncommitted_changes"])
        self.assertFalse(result["is_clean"])
        self.assertEqual(result["unstaged_count"], 1)
        self.assertEqual(result["untracked_count"], 1)

    def test_local_git_status_reports_remote_and_upstream(self) -> None:
        with remote_git_repo() as repo:
            remote_url = run(["git", "remote", "get-url", "origin"], repo).stdout.strip()

            result = detect_local_git_status(str(repo))

        self.assertTrue(result["success"])
        self.assertEqual(result["upstream"], "origin/main")
        self.assertEqual(result["remote_url"], remote_url)

    def test_local_environment_reports_core_fields(self) -> None:
        result = detect_local_environment()

        self.assertTrue(result["success"])
        self.assertTrue(result["os"])
        self.assertTrue(result["architecture"])
        self.assertTrue(result["python_version"])
        self.assertIn("commands", result["raw_data"])
        self.assertIn("git", result["raw_data"]["commands"])
        self.assertIn("python", result["raw_data"]["commands"])

    def test_local_environment_reports_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing"
            result = detect_local_environment(str(missing_path))

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "path_not_found")


class git_repo:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        init_repo(self.repo)
        return self.repo

    def __exit__(self, exc_type, exc, tb) -> None:
        self.temp_dir.cleanup()


class remote_git_repo:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        remote = root / "remote.git"
        repo = root / "repo"
        remote.mkdir()
        repo.mkdir()

        run(["git", "init", "--bare"], remote)
        init_repo(repo)
        run(["git", "remote", "add", "origin", str(remote)], repo)
        run(["git", "push", "-u", "origin", "main"], repo)

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
