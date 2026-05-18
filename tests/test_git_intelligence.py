from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from projectpilot.cli import main as cli_main
from projectpilot.git.analyzer import analyze_status
from projectpilot.git.audit import audit_log_path, read_audit_entries
from projectpilot.git.commit_planner import build_commit_plan
from projectpilot.git.doctor import build_doctor_report
from projectpilot.git.executor import get_diff, get_log, run_fetch
from projectpilot.git.inspector import NotGitRepositoryError, inspect_repository
from projectpilot.git.operation_planner import (
    build_add_plan,
    build_commit_operation_plan,
    build_pull_operation_plan,
    build_push_operation_plan,
)
from projectpilot.git.parser import parse_ahead_behind
from projectpilot.git.recommender import build_recommendations
from projectpilot.git.reporter import render_markdown_report
from projectpilot.git.safe_executor import run_add, run_commit, run_pull, run_push


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

    def test_commit_plan_for_clean_repo(self) -> None:
        with git_repo() as repo:
            plan = build_commit_plan(repo)

            self.assertEqual(plan.summary, "No local changes found.")
            self.assertIsNone(plan.suggested_message)
            self.assertIn("There are no local changes", plan.warnings[0])

    def test_commit_plan_classifies_changes(self) -> None:
        with git_repo() as repo:
            create_mixed_changes(repo)

            plan = build_commit_plan(repo)

            include_paths = {item.path for item in plan.include}
            review_paths = {item.path for item in plan.review}
            exclude_paths = {item.path for item in plan.exclude}

            self.assertIn("projectpilot/feature.py", include_paths)
            self.assertIn("tests/test_feature.py", include_paths)
            self.assertIn("package-lock.json", review_paths)
            self.assertIn(".projectpilot/reports/report.md", exclude_paths)
            self.assertEqual(plan.suggested_message, "Update intelligent Git assistant")

    def test_add_plan_defaults_to_include_files_only(self) -> None:
        with git_repo() as repo:
            create_mixed_changes(repo)

            plan = build_add_plan(repo)

            self.assertTrue(plan.allowed)
            self.assertIn("projectpilot/feature.py", plan.planned_paths)
            self.assertIn("tests/test_feature.py", plan.planned_paths)
            self.assertNotIn("package-lock.json", plan.planned_paths)
            self.assertNotIn(".projectpilot/reports/report.md", plan.planned_paths)
            self.assertIn("package-lock.json", plan.review_paths)
            self.assertIn(".projectpilot/reports/report.md", plan.excluded_paths)

    def test_add_plan_allows_explicit_review_paths(self) -> None:
        with git_repo() as repo:
            create_mixed_changes(repo)

            plan = build_add_plan(repo, include_paths=["package-lock.json"])

            self.assertIn("package-lock.json", plan.planned_paths)

    def test_add_plan_requires_force_for_excluded_paths(self) -> None:
        with git_repo() as repo:
            create_mixed_changes(repo)

            normal_plan = build_add_plan(repo)
            force_plan = build_add_plan(repo, force_include_paths=[".projectpilot/reports/report.md"])

            self.assertNotIn(".projectpilot/reports/report.md", normal_plan.planned_paths)
            self.assertIn(".projectpilot/reports/report.md", force_plan.planned_paths)

    def test_add_apply_stages_only_planned_files(self) -> None:
        with git_repo() as repo:
            create_mixed_changes(repo)

            result = run_add(repo)
            staged = run(["git", "diff", "--cached", "--name-only"], repo).stdout.splitlines()

            self.assertTrue(result.success)
            self.assertIn("projectpilot/feature.py", staged)
            self.assertIn("tests/test_feature.py", staged)
            self.assertNotIn("package-lock.json", staged)
            self.assertNotIn(".projectpilot/reports/report.md", staged)

    def test_add_plan_handles_partially_staged_files(self) -> None:
        with git_repo() as repo:
            (repo / "tracked.txt").write_text("staged\n", encoding="utf-8")
            run(["git", "add", "tracked.txt"], repo)
            (repo / "tracked.txt").write_text("unstaged too\n", encoding="utf-8")

            plan = build_add_plan(repo)

            self.assertTrue(plan.allowed)
            self.assertIn("tracked.txt", plan.planned_paths)

    def test_add_apply_writes_audit_entry(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")

            run_add(repo)
            entries = read_audit_entries(repo)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].operation, "add")
            self.assertEqual(entries[0].command, ["git", "add", "--", "projectpilot/feature.py"])

    def test_dry_run_plan_does_not_write_audit(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")

            build_add_plan(repo)

            self.assertFalse(audit_log_path(repo).exists())

    def test_commit_plan_blocks_without_staged_files(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")

            plan = build_commit_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("No staged files", plan.blockers[0])

    def test_commit_plan_uses_staged_files_only(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            (repo / "notes.md").write_text("draft\n", encoding="utf-8")
            run(["git", "add", "projectpilot/feature.py"], repo)

            plan = build_commit_operation_plan(repo)

            self.assertTrue(plan.allowed)
            self.assertEqual(plan.planned_paths, ["projectpilot/feature.py"])
            self.assertEqual(plan.suggested_message, "Update intelligent Git assistant")
            self.assertTrue(any("Untracked files" in warning for warning in plan.warnings))

    def test_commit_plan_blocks_staged_excluded_files(self) -> None:
        with git_repo() as repo:
            (repo / ".projectpilot" / "reports").mkdir(parents=True)
            (repo / ".projectpilot" / "reports" / "report.md").write_text("generated\n", encoding="utf-8")
            run(["git", "add", ".projectpilot/reports/report.md"], repo)

            plan = build_commit_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("Excluded-category files are staged", "; ".join(plan.blockers))

    def test_commit_apply_creates_commit(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            run(["git", "add", "projectpilot/feature.py"], repo)
            before_commit = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()

            result = run_commit(repo, message="Add demo feature")
            after_commit = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
            status = inspect_repository(repo)

            self.assertTrue(result.success)
            self.assertNotEqual(before_commit, after_commit)
            self.assertTrue(status.is_clean)
            self.assertIn("Add demo feature", run(["git", "log", "-1", "--pretty=%s"], repo).stdout)

    def test_commit_apply_writes_audit_entry(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            run(["git", "add", "projectpilot/feature.py"], repo)

            run_commit(repo, message="Add demo feature")
            entries = read_audit_entries(repo, operation="commit")

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].operation, "commit")
            self.assertNotEqual(entries[0].before_commit, entries[0].after_commit)
            self.assertTrue(entries[0].after_clean)

    def test_audit_limit_and_operation_filter(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")

            run_add(repo)
            run_commit(repo, message="Add demo feature")

            latest = read_audit_entries(repo, limit=1)
            add_entries = read_audit_entries(repo, operation="add")

            self.assertEqual(len(latest), 1)
            self.assertEqual(latest[0].operation, "commit")
            self.assertEqual(len(add_entries), 1)
            self.assertEqual(add_entries[0].operation, "add")

    def test_audit_cli_outputs_json(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            run_add(repo)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = cli_main(["git", "audit", str(repo), "--operation", "add", "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["operation"], "add")

    def test_push_plan_blocks_without_upstream(self) -> None:
        with git_repo() as repo:
            plan = build_push_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("upstream", "; ".join(plan.blockers))

    def test_push_plan_allows_ahead_branch(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")

            plan = build_push_operation_plan(repo)

            self.assertTrue(plan.allowed)
            self.assertEqual(plan.command, ["git", "push"])
            self.assertEqual(plan.planned_paths, ["main -> origin/main"])

    def test_push_apply_pushes_commits(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")

            result = run_push(repo)
            status = inspect_repository(repo)
            entries = read_audit_entries(repo, operation="push")

            self.assertTrue(result.success)
            self.assertEqual(status.ahead, 0)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].operation, "push")

    def test_push_dry_run_plan_does_not_push(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")

            plan = build_push_operation_plan(repo)
            status = inspect_repository(repo)

            self.assertTrue(plan.allowed)
            self.assertEqual(status.ahead, 1)

    def test_push_plan_blocks_diverged_branch(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")
            create_remote_commit(repo, "peer.txt", "peer\n", "peer commit")
            run(["git", "fetch"], repo)
            plan = build_push_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("diverged", "; ".join(plan.blockers))

    def test_pull_plan_blocks_without_upstream(self) -> None:
        with git_repo() as repo:
            plan = build_pull_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("upstream", "; ".join(plan.blockers))

    def test_pull_plan_allows_behind_clean_branch(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            plan = build_pull_operation_plan(repo)

            self.assertTrue(plan.allowed)
            self.assertEqual(plan.command, ["git", "pull", "--ff-only"])
            self.assertEqual(plan.planned_paths, ["origin/main -> main"])

    def test_pull_apply_updates_branch(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            result = run_pull(repo)
            status = inspect_repository(repo)
            entries = read_audit_entries(repo, operation="pull")

            self.assertTrue(result.success)
            self.assertEqual(status.behind, 0)
            self.assertTrue((repo / "remote.txt").exists())
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].operation, "pull")

    def test_pull_dry_run_plan_does_not_pull(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            plan = build_pull_operation_plan(repo)
            status = inspect_repository(repo)

            self.assertTrue(plan.allowed)
            self.assertEqual(status.behind, 1)
            self.assertFalse((repo / "remote.txt").exists())

    def test_pull_plan_blocks_dirty_worktree(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)
            (repo / "local-draft.txt").write_text("draft\n", encoding="utf-8")

            plan = build_pull_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("Working tree must be clean", "; ".join(plan.blockers))

    def test_pull_plan_blocks_diverged_branch(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            plan = build_pull_operation_plan(repo)

            self.assertFalse(plan.allowed)
            self.assertIn("diverged", "; ".join(plan.blockers))

    def test_doctor_reports_healthy_repository(self) -> None:
        with remote_git_repo() as repo:
            report = build_doctor_report(repo)

            self.assertEqual(report.health, "healthy")
            self.assertEqual(report.risk, "low")
            self.assertTrue(report.is_clean)
            self.assertFalse(report.can_add)
            self.assertFalse(report.can_commit)
            self.assertFalse(report.can_push)
            self.assertFalse(report.can_pull)
            self.assertEqual(report.recommended_next_step, "No Git action needed right now.")

    def test_doctor_reports_attention_without_upstream(self) -> None:
        with git_repo() as repo:
            report = build_doctor_report(repo)

            self.assertEqual(report.health, "attention")
            self.assertEqual(report.risk, "medium")
            self.assertTrue(any("upstream" in finding for finding in report.findings))
            self.assertIn("Configure a remote", report.recommended_next_step)

    def test_doctor_reports_attention_for_dirty_worktree(self) -> None:
        with git_repo() as repo:
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")

            report = build_doctor_report(repo)

            self.assertEqual(report.health, "attention")
            self.assertFalse(report.is_clean)
            self.assertTrue(report.can_add)
            self.assertIn("commit-plan", report.recommended_next_step)

    def test_doctor_reports_blocked_for_diverged_branch(self) -> None:
        with remote_git_repo() as repo:
            create_local_commit(repo, "local.txt", "local\n", "local commit")
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)

            report = build_doctor_report(repo)

            self.assertEqual(report.health, "blocked")
            self.assertTrue(any("diverged" in finding for finding in report.findings))
            self.assertIn("resolve divergence", report.recommended_next_step)

    def test_doctor_reports_blocked_for_dirty_behind_branch(self) -> None:
        with remote_git_repo() as repo:
            create_remote_commit(repo, "remote.txt", "remote\n", "remote commit")
            run(["git", "fetch"], repo)
            (repo / "tracked.txt").write_text("local draft\n", encoding="utf-8")

            report = build_doctor_report(repo)

            self.assertEqual(report.health, "blocked")
            self.assertFalse(report.can_pull)
            self.assertIn("commit-plan", report.recommended_next_step)

    def test_doctor_includes_recent_audit_operation(self) -> None:
        with git_repo() as repo:
            (repo / "projectpilot").mkdir()
            (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
            run_add(repo)

            report = build_doctor_report(repo)

            self.assertEqual(report.last_audit_operation, "add")
            self.assertTrue(any("Recent ProjectPilot operation: add success" in finding for finding in report.findings))

    def test_doctor_cli_outputs_json(self) -> None:
        with git_repo() as repo:
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = cli_main(["git", "doctor", str(repo), "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(data["health"], "attention")
            self.assertEqual(data["branch"], "main")


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


def create_mixed_changes(repo: Path) -> None:
    (repo / "projectpilot").mkdir()
    (repo / "projectpilot" / "feature.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / "tests" / "test_feature.py").parent.mkdir()
    (repo / "tests" / "test_feature.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (repo / ".projectpilot" / "reports").mkdir(parents=True)
    (repo / ".projectpilot" / "reports" / "report.md").write_text("generated\n", encoding="utf-8")
    (repo / "package-lock.json").write_text("{}\n", encoding="utf-8")


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
