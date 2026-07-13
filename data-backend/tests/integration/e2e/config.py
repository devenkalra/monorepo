from dataclasses import dataclass
import os


@dataclass(frozen=True)
class E2EConfig:
    base_url: str
    email: str
    password: str
    timeout_seconds: int



def load_config() -> E2EConfig:
    return E2EConfig(
        base_url=os.environ.get("E2E_BASE_URL", "http://localhost:8000").rstrip("/"),
        email=os.environ.get("E2E_EMAIL", "e2e@kalra.com"),
        password=os.environ.get("E2E_PASSWORD", "TestPassword"),
        timeout_seconds=int(os.environ.get("E2E_TIMEOUT_SECONDS", "20")),
    )
