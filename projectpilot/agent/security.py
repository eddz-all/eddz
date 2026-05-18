from __future__ import annotations

from pathlib import Path


class PathNotAllowedError(ValueError):
    pass


def resolve_allowed_project_path(project_path: str, allowed_root: Path) -> Path:
    root = allowed_root.expanduser().resolve()
    target = Path(project_path).expanduser()
    if not target.is_absolute():
        target = root / target
    resolved = target.resolve(strict=False)

    if not resolved.is_relative_to(root):
        raise PathNotAllowedError(f"Project path is outside allowed root: {resolved}")
    return resolved
