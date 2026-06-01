from __future__ import annotations

from pathlib import Path
from typing import Any


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


def validate_remote_project_path(project_path: str, allowed_paths: Any = None) -> str:
    """Validate an absolute remote project path and optional allowed path prefixes."""
    value = str(project_path or "").strip()
    if not value:
        raise ValueError("project_path is required.")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("project_path contains invalid characters.")
    if not value.startswith("/"):
        raise ValueError("project_path must be an absolute remote path.")

    if allowed_paths is None:
        return value
    if not isinstance(allowed_paths, list):
        raise ValueError("allowed_paths must be a string array.")

    normalized_roots: list[str] = []
    for raw_root in allowed_paths:
        root = str(raw_root or "").strip().rstrip("/")
        if not root:
            continue
        if "\x00" in root or "\n" in root or "\r" in root:
            raise ValueError("allowed_paths contains invalid characters.")
        if not root.startswith("/"):
            raise ValueError("allowed_paths entries must be absolute remote paths.")
        normalized_roots.append(root or "/")

    for root in normalized_roots:
        if root == "/" or value == root or value.startswith(f"{root}/"):
            return value

    raise PathNotAllowedError(f"Remote project path is outside allowed paths: {value}")
