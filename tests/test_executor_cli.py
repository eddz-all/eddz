from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from projectpilot.executor.cli import main as executor_main


class ExecutorCliTests(unittest.TestCase):
    def test_executor_cli_version(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = executor_main(["--version"])

        self.assertEqual(exit_code, 0)
        self.assertIn("projectpilot-executor", output.getvalue())

    def test_executor_cli_forwards_ssh_hosts_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ssh_config = Path(temp_dir) / "config"
            ssh_config.write_text("Host dev-server\n  HostName 127.0.0.1\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = executor_main(["ssh-hosts", "--ssh-config", str(ssh_config), "--json"])

            data = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(data["hosts"], ["dev-server"])


if __name__ == "__main__":
    unittest.main()
