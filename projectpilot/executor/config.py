from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutorConfig:
    server_url: str
    token: str
    executor_id: str
    allowed_root: Path
    interval: float = 5.0
    mode: str = "local"

    def to_dict(self, mask_token: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_root"] = str(self.allowed_root)
        if mask_token:
            data["token"] = mask_token_value(self.token)
        return data


def default_config_path() -> Path:
    override = os.environ.get("PROJECTPILOT_EXECUTOR_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".projectpilot" / "executor.json"


def default_executor_id() -> str:
    return socket.gethostname() or "local-machine"


def load_config(path: Path | None = None) -> ExecutorConfig:
    config_path = (path or default_config_path()).expanduser()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return ExecutorConfig(
        server_url=str(data["server_url"]).rstrip("/"),
        token=str(data["token"]),
        executor_id=str(data["executor_id"]),
        allowed_root=Path(data["allowed_root"]).expanduser(),
        interval=float(data.get("interval", 5.0)),
        mode=str(data.get("mode", "local")),
    )


def save_config(config: ExecutorConfig, path: Path | None = None) -> Path:
    config_path = (path or default_config_path()).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except OSError:
        pass
    return config_path


def build_config(
    server_url: str,
    token: str,
    executor_id: str | None,
    allowed_root: str | Path,
    interval: float,
    mode: str = "local",
) -> ExecutorConfig:
    if not server_url:
        raise ValueError("server_url is required.")
    if not token:
        raise ValueError("token is required.")
    if interval <= 0:
        raise ValueError("interval must be greater than 0.")

    root = Path(allowed_root).expanduser()
    if not root.exists():
        raise ValueError(f"allowed_root does not exist: {root}")

    return ExecutorConfig(
        server_url=server_url.rstrip("/"),
        token=token,
        executor_id=executor_id or default_executor_id(),
        allowed_root=root.resolve(),
        interval=interval,
        mode=mode,
    )


def mask_token_value(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"
