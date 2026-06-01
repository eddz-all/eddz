import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: str = ".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class AISettings:
    provider: str
    api_key: str
    model: str
    base_url: str


@dataclass
class ExecutorSettings:
    shared_token: str


def get_ai_settings() -> AISettings:
    load_env_file()

    return AISettings(
        provider=os.getenv("AI_PROVIDER", "mock"),
        api_key=os.getenv("AI_API_KEY", ""),
        model=os.getenv("AI_MODEL", "qwen-plus"),
        base_url=os.getenv(
            "AI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    )


def get_executor_settings() -> ExecutorSettings:
    load_env_file()
    return ExecutorSettings(
        shared_token=os.getenv("EXECUTOR_SHARED_TOKEN", "dev-token"),
    )
