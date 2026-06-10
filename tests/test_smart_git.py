from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from projectpilot.cli import main as cli_main
from projectpilot.git.state_map import build_state_map
from projectpilot.git.sync_planner import build_sync_plan
from projectpilot.integration.smart_git import analyze_repository


class SmartGitTests(unittest.TestCase):
    def test_state_map_groups_working_tree_staged_and_untracked_files(self) -> None:
        with git_repo() as repo:
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            run(["git", "add", "staged.txt"], repo)

            state_map = build_state_map(repo)

            self.assertEqual(state_map.risk, "medium")
            self.assertEqual([item.path for item in state_map.working_tree], ["tracked.txt"])
            self.assertEqual([item.path for item in state_map.staged], ["staged.txt"])
            self.assertEqual([item.path for item in state_map.untracked], ["new.txt"])
            self.assertTrue(any("working tree" in step.lower() for step in state_map.next_steps))

    def test_map_cli_outputs_json(self) -> None:
        with git_repo() as repo:
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(["git", "map", str(repo), "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(data["branch"], "main")
            self.assertIn("working_tree", data)
            self.assertIn("remote", data)

    def test_sync_plan_allows_fast_forward_pull_when_clean_and_behind(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            sync_plan = build_sync_plan(repo)

            self.assertEqual(sync_plan.sync_state, "behind")
            self.assertEqual(sync_plan.working_tree_state, "clean")
            self.assertTrue(sync_plan.can_pull_ff_only)
            self.assertFalse(sync_plan.can_push)
            self.assertEqual(sync_plan.recommended_action, "pull_ff_only")

    def test_sync_plan_blocks_diverged_branch(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            sync_plan = build_sync_plan(repo)

            self.assertEqual(sync_plan.sync_state, "diverged")
            self.assertEqual(sync_plan.risk, "high")
            self.assertFalse(sync_plan.can_push)
            self.assertFalse(sync_plan.can_pull_ff_only)
            self.assertTrue(any(item.operation == "push" for item in sync_plan.blocked_operations))

    def test_analyze_repository_returns_default_reports(self) -> None:
        with git_repo() as repo:
            analysis = analyze_repository(repo)

            self.assertTrue(analysis["success"])
            self.assertEqual(analysis["schema_version"], "smart-git.v1")
            self.assertEqual(analysis["branch"], "main")
            self.assertIn("status", analysis["reports"])
            self.assertIn("doctor", analysis["reports"])
            self.assertIn("map", analysis["reports"])
            self.assertIn("sync_plan", analysis["reports"])
            self.assertIn("commit_plan", analysis["reports"])
            self.assertIn("issue_report", analysis)
            self.assertEqual(analysis["issue_report"]["schema_version"], "git-issues.v1")
            self.assertEqual(len(analysis["playbook"]), 10)

    def test_analyze_repository_classifies_merge_conflict(self) -> None:
        with git_repo() as repo:
            run(["git", "switch", "-c", "feature"], repo)
            (repo / "tracked.txt").write_text("feature\n", encoding="utf-8")
            run(["git", "commit", "-am", "feature change"], repo)
            run(["git", "switch", "main"], repo)
            (repo / "tracked.txt").write_text("main\n", encoding="utf-8")
            run(["git", "commit", "-am", "main change"], repo)
            result = subprocess.run(
                ["git", "merge", "feature"],
                cwd=str(repo),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

            analysis = analyze_repository(repo)
            issue_codes = {item["code"] for item in analysis["issues"]}

            self.assertIn("merge_conflict", issue_codes)
            self.assertEqual(analysis["risk"], "high")

    def test_analyze_repository_classifies_dirty_behind_branch(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)
            (repo / "tracked.txt").write_text("local draft\n", encoding="utf-8")

            analysis = analyze_repository(repo)
            issue_codes = {item["code"] for item in analysis["issues"]}

            self.assertIn("local_changes_block", issue_codes)
            self.assertIn("push_rejected", issue_codes)

    def test_analyze_repository_classifies_detached_head(self) -> None:
        with git_repo() as repo:
            run(["git", "checkout", "--detach", "HEAD"], repo)

            analysis = analyze_repository(repo)
            issue_codes = {item["code"] for item in analysis["issues"]}

            self.assertIn("detached_head", issue_codes)

    def test_analyze_repository_classifies_accidental_and_tracked_ignored_files(self) -> None:
        with git_repo() as repo:
            (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            (repo / "dist").mkdir()
            (repo / "dist" / "bundle.js").write_text("compiled\n", encoding="utf-8")
            run(["git", "add", "dist/bundle.js"], repo)
            run(["git", "commit", "-m", "track generated output"], repo)
            (repo / "dist" / "bundle.js").write_text("compiled again\n", encoding="utf-8")

            analysis = analyze_repository(repo)
            issue_codes = {item["code"] for item in analysis["issues"]}

            self.assertIn("accidental_files", issue_codes)
            self.assertIn("gitignore_not_effective", issue_codes)

    def test_analyze_cli_accepts_include_aliases(self) -> None:
        with git_repo() as repo:
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(["git", "analyze", str(repo), "--include", "map", "sync-plan", "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(data["success"])
            self.assertEqual(set(data["reports"]), {"map", "sync_plan"})

    def test_analyze_repository_reports_non_git_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis = analyze_repository(temp_dir)

            self.assertFalse(analysis["success"])
            self.assertEqual(analysis["error_type"], "not_git_repository")


class git_repo:
    def __enter__(self) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        repo = Path(self.temp_dir.name)
        init_repo(repo)
        self.repo = repo
        return repo

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


def create_local_commit(repo: Path, relative_path: str, content: str, message: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run(["git", "add", relative_path], repo)
    run(["git", "commit", "-m", message], repo)


def create_remote_commit(repo: Path, relative_path: str, content: str, message: str) -> None:
    with tempfile.TemporaryDirectory() as peer_dir:
        peer = Path(peer_dir)
        remote_url = run(["git", "remote", "get-url", "origin"], repo).stdout.strip()
        run(["git", "clone", remote_url, "."], peer)
        run(["git", "checkout", "main"], peer)
        run(["git", "config", "user.name", "ProjectPilot Peer"], peer)
        run(["git", "config", "user.email", "peer@example.test"], peer)
        create_local_commit(peer, relative_path, content, message)
        run(["git", "push", "origin", "main"], peer)


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
