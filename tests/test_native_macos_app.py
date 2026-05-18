from __future__ import annotations

import os
import unittest
from pathlib import Path


class NativeMacOSAppTests(unittest.TestCase):
    def test_native_package_and_run_script_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package = root / "macos" / "ProjectPilotAgentNative" / "Package.swift"
        script = root / "script" / "build_and_run.sh"

        self.assertTrue(package.exists())
        self.assertTrue(script.exists())
        self.assertTrue(os.access(script, os.X_OK))

    def test_run_button_environment_points_to_script(self) -> None:
        root = Path(__file__).resolve().parents[1]
        environment = root / ".codex" / "environments" / "environment.toml"

        self.assertIn("./script/build_and_run.sh", environment.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
