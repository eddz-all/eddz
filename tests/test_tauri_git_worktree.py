from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "projectpilot-tauri-app" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.git_worktree_service import inspect_git_worktree, unavailable_git_worktree  # noqa: E402


class TauriGitWorktreeTests(unittest.TestCase):
    def test_remote_path_payload_does_not_claim_git_state(self) -> None:
        payload = unavailable_git_worktree(
            "/opt/projectpilot",
            reason="remote_path",
            message="Remote executor path requires an executor snapshot.",
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["reason"], "remote_path")
        self.assertIsNone(payload["branch"])
        self.assertIsNone(payload["repo_path"])
        self.assertEqual(payload["ahead"], 0)
        self.assertEqual(payload["behind"], 0)
        self.assertEqual(payload["refs"], [])
        self.assertEqual(payload["commits"], [])
        self.assertEqual(payload["worktree"]["state"], "unavailable")

    def test_missing_local_path_is_structured_unavailable(self) -> None:
        missing_path = "/tmp/projectpilot-definitely-missing-git-worktree"
        payload = inspect_git_worktree(missing_path)

        self.assertFalse(payload["success"])
        self.assertEqual(payload["reason"], "path_missing")
        self.assertEqual(payload["project_path"], missing_path)
        self.assertIn("does not exist", payload["message"])
        self.assertIsNone(payload["branch"])
        self.assertEqual(payload["worktree"]["counts"]["unstaged"], 0)


if __name__ == "__main__":
    unittest.main()
