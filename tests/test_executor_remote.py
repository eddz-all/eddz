from __future__ import annotations

import unittest
from unittest.mock import patch

from projectpilot.executor.remote import (
    apply_remote_git_operation,
    build_remote_git_command,
    check_connection,
    detect_remote_environment,
    detect_remote_git_status,
    list_ssh_hosts,
    normalize_host,
    normalize_remote_path,
    parse_ssh_g_output,
    run_remote_script,
    sha256_text,
)


class ExecutorRemoteTests(unittest.TestCase):
    def test_normalize_host_rejects_shell_like_values(self) -> None:
        with self.assertRaises(ValueError):
            normalize_host("-oProxyCommand=bad")
        with self.assertRaises(ValueError):
            normalize_host("prod server")

    def test_normalize_remote_path_requires_absolute_path(self) -> None:
        with self.assertRaises(ValueError):
            normalize_remote_path("relative/app")
        self.assertEqual(normalize_remote_path("/srv/app"), "/srv/app")

    def test_check_connection_uses_ssh_result(self) -> None:
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": "projectpilot-ok", "stderr": "", "exit_code": 0}

            result = check_connection("dev-server")

        self.assertTrue(result["success"])
        self.assertTrue(result["connected"])
        self.assertEqual(result["ssh_host"], "dev-server")
        self.assertEqual(result["message"], "Connection successful")
        self.assertIn("latency_ms", result)
        run_ssh_command.assert_called_once_with("dev-server", "echo projectpilot-ok", timeout=15, auth_mode="key")

    def test_detect_remote_git_status_parses_basic_snapshot(self) -> None:
        stdout = "\n".join(
            [
                "status_begin",
                "# branch.oid abc123",
                "# branch.head main",
                "# branch.upstream origin/main",
                "# branch.ab +0 -2",
                "1 .M N... 100644 100644 100644 aaaaaa bbbbbb app.py",
                "? scratch.txt",
                "status_end",
                "remotes_begin",
                "origin\tgit@example.com:team/app.git (fetch)",
                "origin\tgit@example.com:team/app.git (push)",
                "remotes_end",
                "last_commit=abc123 update app",
            ]
        )
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": stdout, "stderr": "", "exit_code": 0}

            result = detect_remote_git_status("prod-server", "/srv/app")

        self.assertTrue(result["success"])
        self.assertEqual(result["ssh_host"], "prod-server")
        self.assertEqual(result["branch"], "main")
        self.assertEqual(result["commit"], "abc123")
        self.assertEqual(result["upstream"], "origin/main")
        self.assertEqual(result["remote_url"], "git@example.com:team/app.git")
        self.assertEqual(result["ahead"], 0)
        self.assertEqual(result["behind"], 2)
        self.assertFalse(result["is_clean"])
        self.assertEqual(result["state"], "dirty")
        self.assertEqual(result["unstaged_count"], 1)
        self.assertEqual(result["untracked_count"], 1)
        self.assertEqual(result["last_commit"], "abc123 update app")
        self.assertTrue(result["has_uncommitted_changes"])
        self.assertEqual(result["remotes"]["origin"], ["git@example.com:team/app.git"])

    def test_detect_remote_environment_parses_key_value_lines(self) -> None:
        stdout = "\n".join(
            [
                "os=Linux",
                "architecture=x86_64",
                "git_version=2.43.0",
                "npm_version=10.8.0",
                "docker_installed=true",
                "docker_version=26.1.0",
                "docker_running=false",
                "docker_compose_version=2.27.0",
                "cuda_version=12.4",
                "project_path_exists=true",
                "disk_usage=68%",
            ]
        )
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": stdout, "stderr": "", "exit_code": 0}

            result = detect_remote_environment("prod-server", "/srv/app")

        self.assertTrue(result["success"])
        self.assertEqual(result["os"], "Linux")
        self.assertTrue(result["docker_installed"])
        self.assertFalse(result["docker_running"])
        self.assertEqual(result["npm_version"], "10.8.0")
        self.assertEqual(result["docker_version"], "26.1.0")
        self.assertEqual(result["docker_compose_version"], "2.27.0")
        self.assertEqual(result["cuda_version"], "12.4")
        self.assertTrue(result["project_path_exists"])
        self.assertEqual(result["disk_usage"], "68%")

    def test_list_ssh_hosts_reads_simple_host_entries(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config"
            config_path.write_text(
                "\n".join(
                    [
                        "Host dev-server prod-server",
                        "  HostName 10.0.0.10",
                        "Host *",
                        "  ForwardAgent no",
                        "Host internal-*",
                        "  User deploy",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(list_ssh_hosts(config_path), ["dev-server", "prod-server"])

    def test_parse_ssh_g_output_collects_identity_files(self) -> None:
        parsed = parse_ssh_g_output(
            "\n".join(
                [
                    "hostname prod.example.com",
                    "user deploy",
                    "port 2222",
                    "identityfile ~/.ssh/id_ed25519",
                    "identityfile ~/.ssh/prod",
                ]
            )
        )

        self.assertEqual(parsed["hostname"], "prod.example.com")
        self.assertEqual(parsed["identityfile"], ["~/.ssh/id_ed25519", "~/.ssh/prod"])

    def test_build_remote_git_command_uses_whitelist(self) -> None:
        self.assertEqual(build_remote_git_command("pull", {}), ["git", "pull", "--ff-only"])
        self.assertEqual(
            build_remote_git_command("switch", {"target": "feature/demo", "create": True, "start_point": "main"}),
            ["git", "switch", "-c", "feature/demo", "main"],
        )
        self.assertEqual(
            build_remote_git_command("stash", {"include_untracked": True, "message": "save draft"}),
            ["git", "stash", "push", "--include-untracked", "-m", "save draft"],
        )

    def test_build_remote_git_command_rejects_option_like_refs(self) -> None:
        with self.assertRaises(ValueError):
            build_remote_git_command("switch", {"target": "-bad"})

    def test_apply_remote_git_operation_runs_preflight_command_and_after_snapshot(self) -> None:
        before = {
            "success": True,
            "host": "prod-server",
            "project_path": "/srv/app",
            "branch": "main",
            "commit": "before",
            "upstream": "origin/main",
            "is_clean": True,
            "ahead": 0,
            "behind": 1,
            "state": "behind",
        }
        after = {
            "success": True,
            "host": "prod-server",
            "project_path": "/srv/app",
            "branch": "main",
            "commit": "after",
            "upstream": "origin/main",
            "is_clean": True,
            "ahead": 0,
            "behind": 0,
            "state": "clean",
        }
        with patch("projectpilot.executor.remote.detect_remote_git_status", side_effect=[before, after]):
            with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
                run_ssh_command.return_value = {"stdout": "updated\n", "stderr": "", "exit_code": 0}

                result = apply_remote_git_operation(
                    "prod-server",
                    "/srv/app",
                    "pull",
                    expected_command=["git", "pull", "--ff-only"],
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["command"], ["git", "pull", "--ff-only"])
        self.assertEqual(result["before"]["commit"], "before")
        self.assertEqual(result["after"]["commit"], "after")
        run_ssh_command.assert_called_once_with(
            "prod-server",
            "cd /srv/app && git pull --ff-only",
            timeout=30,
            auth_mode="key",
        )

    def test_apply_remote_git_operation_rejects_command_mismatch(self) -> None:
        result = apply_remote_git_operation(
            "prod-server",
            "/srv/app",
            "pull",
            expected_command=["git", "push"],
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "command_mismatch")

    def test_apply_remote_git_operation_blocks_unsafe_pull_state(self) -> None:
        before = {
            "success": True,
            "host": "prod-server",
            "project_path": "/srv/app",
            "branch": "main",
            "commit": "before",
            "upstream": "origin/main",
            "is_clean": False,
            "ahead": 1,
            "behind": 1,
            "state": "diverged",
        }
        with patch("projectpilot.executor.remote.detect_remote_git_status", return_value=before):
            with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
                result = apply_remote_git_operation(
                    "prod-server",
                    "/srv/app",
                    "pull",
                    expected_command=["git", "pull", "--ff-only"],
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "remote_git_operation_blocked")
        self.assertIn("pull requires a clean working tree", result["blockers"])
        run_ssh_command.assert_not_called()

    def test_run_remote_script_sends_script_over_stdin(self) -> None:
        script = "echo hello\n"
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": "hello\n", "stderr": "", "exit_code": 0}

            result = run_remote_script(
                "prod-server",
                script,
                project_path="/srv/app",
                env={"APP_ENV": "test"},
                args=["one"],
                expected_sha256=sha256_text(script),
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["ssh_host"], "prod-server")
        self.assertEqual(result["script_sha256"], sha256_text(script))
        run_ssh_command.assert_called_once_with(
            "prod-server",
            "cd /srv/app && env APP_ENV=test bash -s -- one",
            timeout=60,
            stdin_data=script,
            auth_mode="key",
        )

    def test_run_remote_script_allows_password_auth_mode(self) -> None:
        script = "whoami\n"
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": "hzy\n", "stderr": "", "exit_code": 0}

            result = run_remote_script(
                "ubuntu",
                script,
                project_path="/home/hzy",
                auth_mode="password",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["ssh_auth_mode"], "password")
        run_ssh_command.assert_called_once_with(
            "ubuntu",
            "cd /home/hzy && bash -s --",
            timeout=60,
            stdin_data=script,
            auth_mode="password",
        )

    def test_run_remote_script_rejects_hash_mismatch(self) -> None:
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            result = run_remote_script(
                "prod-server",
                "echo hello\n",
                expected_sha256="wrong",
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "script_hash_mismatch")
        run_ssh_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
