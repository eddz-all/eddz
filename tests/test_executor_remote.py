from __future__ import annotations

import unittest
from unittest.mock import patch

from projectpilot.executor.remote import (
    check_connection,
    detect_remote_environment,
    detect_remote_git_status,
    list_ssh_hosts,
    normalize_host,
    normalize_remote_path,
    parse_ssh_g_output,
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
        run_ssh_command.assert_called_once_with("dev-server", "printf projectpilot-ok", timeout=15)

    def test_detect_remote_git_status_parses_basic_snapshot(self) -> None:
        stdout = "\n".join(
            [
                "branch=main",
                "commit=abc123",
                "status_begin",
                "## main...origin/main",
                " M app.py",
                "remotes_begin",
                "origin\tgit@example.com:team/app.git (fetch)",
            ]
        )
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": stdout, "stderr": "", "exit_code": 0}

            result = detect_remote_git_status("prod-server", "/srv/app")

        self.assertTrue(result["success"])
        self.assertEqual(result["branch"], "main")
        self.assertEqual(result["commit"], "abc123")
        self.assertTrue(result["has_uncommitted_changes"])
        self.assertIn("origin\tgit@example.com:team/app.git (fetch)", result["remotes"])

    def test_detect_remote_environment_parses_key_value_lines(self) -> None:
        stdout = "\n".join(
            [
                "os=Linux",
                "architecture=x86_64",
                "git_version=2.43.0",
                "docker_installed=true",
                "docker_running=false",
            ]
        )
        with patch("projectpilot.executor.remote.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = {"stdout": stdout, "stderr": "", "exit_code": 0}

            result = detect_remote_environment("prod-server", "/srv/app")

        self.assertTrue(result["success"])
        self.assertEqual(result["os"], "Linux")
        self.assertTrue(result["docker_installed"])
        self.assertFalse(result["docker_running"])

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


if __name__ == "__main__":
    unittest.main()
