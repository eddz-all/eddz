from __future__ import annotations

import json

from demo_seed import recreate_demo_workspaces, seed_backend


def seed_data() -> dict:
    workspace_paths = recreate_demo_workspaces()
    return seed_backend(workspace_paths)


if __name__ == "__main__":
    result = seed_data()
    print(json.dumps(result, indent=2))
