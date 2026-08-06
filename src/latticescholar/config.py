from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_FROZEN = getattr(sys, "frozen", False)
_MEIPASS = Path(getattr(sys, "_MEIPASS", "")) if _FROZEN else None

PACKAGE_DIR = _MEIPASS / "latticescholar" if _MEIPASS else Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parents[1] if not _FROZEN else PACKAGE_DIR

_DEFAULT_DATA_DIR = (
    str(Path.home() / ".latticescholar") if _FROZEN else str(PROJECT_DIR / ".data")
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "LatticeScholar"
    app_version: str = "0.9.4"
    host: str = os.getenv("LATTICE_HOST", "127.0.0.1")
    port: int = int(os.getenv("LATTICE_PORT", "8765"))
    data_dir: Path = Path(os.getenv("LATTICE_DATA_DIR", _DEFAULT_DATA_DIR))
    cache_ttl_seconds: int = int(os.getenv("LATTICE_CACHE_TTL", "86400"))
    request_timeout_seconds: float = float(os.getenv("LATTICE_REQUEST_TIMEOUT", "18"))
    crossref_email: str = os.getenv("CROSSREF_EMAIL", "")
    semantic_scholar_api_key: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    openalex_api_key: str = os.getenv("OPENALEX_API_KEY", "")
    ncbi_api_key: str = os.getenv("NCBI_API_KEY", "")
    ncbi_email: str = os.getenv("NCBI_EMAIL", "")
    wos_api_key: str = os.getenv("WOS_API_KEY", "")
    access_password: str = os.getenv("LATTICE_ACCESS_PASSWORD", "")
    session_secret: str = os.getenv("LATTICE_SESSION_SECRET", "")
    secure_cookies: bool = _env_bool("LATTICE_SECURE_COOKIES", False)
    auth_mode: str = os.getenv("LATTICE_AUTH_MODE", "accounts").lower()
    dev_auth: bool = _env_bool(
        "LATTICE_DEV_AUTH",
        default=os.getenv("LATTICE_DEV_AUTH") is None and not os.getenv("LATTICE_SMTP_HOST", "").strip(),
    )
    admin_emails: str = os.getenv("LATTICE_ADMIN_EMAILS", "")
    smtp_host: str = os.getenv("LATTICE_SMTP_HOST", "")
    smtp_port: int = int(os.getenv("LATTICE_SMTP_PORT", "587"))
    smtp_username: str = os.getenv("LATTICE_SMTP_USERNAME", "")
    smtp_password: str = os.getenv("LATTICE_SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("LATTICE_SMTP_FROM_EMAIL", "")
    smtp_use_tls: bool = _env_bool("LATTICE_SMTP_USE_TLS", True)
    public_base_url: str = os.getenv("LATTICE_PUBLIC_BASE_URL", "http://127.0.0.1:8765")
    repository_url: str = os.getenv("LATTICE_REPOSITORY_URL", "https://github.com/CBarran498/LatticeScholar")
    policy_sync_interval_hours: float = float(
        os.getenv("LATTICE_POLICY_SYNC_INTERVAL_HOURS", "0")
    )
    policy_sync_source_ids: str = os.getenv(
        "LATTICE_POLICY_SYNC_SOURCE_IDS", "state-council,most,nsfc,moe"
    )
    llm_provider: str = os.getenv("LATTICE_LLM_PROVIDER", "none").lower()
    llm_base_url: str = os.getenv("LATTICE_LLM_BASE_URL", "http://127.0.0.1:11434")
    llm_api_key: str = os.getenv("LATTICE_LLM_API_KEY", "")
    llm_model: str = os.getenv("LATTICE_LLM_MODEL", "qwen2.5:7b")
    llm_max_input_chars: int = int(os.getenv("LATTICE_LLM_MAX_INPUT_CHARS", "32000"))
    llm_max_output_tokens: int = int(os.getenv("LATTICE_LLM_MAX_OUTPUT_TOKENS", "8000"))
    allow_remote_llm: bool = _env_bool("LATTICE_ALLOW_REMOTE_LLM", False)
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv(
        "LATTICE_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    deepseek_fast_model: str = os.getenv(
        "LATTICE_DEEPSEEK_FAST_MODEL", "deepseek-v4-flash"
    )
    deepseek_reasoning_model: str = os.getenv(
        "LATTICE_DEEPSEEK_REASONING_MODEL", "deepseek-v4-pro"
    )
    deepseek_routing: str = os.getenv("LATTICE_DEEPSEEK_ROUTING", "balanced").lower()
    deepseek_thinking: str = os.getenv("LATTICE_DEEPSEEK_THINKING", "adaptive").lower()
    deepseek_reasoning_effort: str = os.getenv(
        "LATTICE_DEEPSEEK_REASONING_EFFORT", "high"
    ).lower()
    deepseek_timeout_seconds: float = float(
        os.getenv("LATTICE_DEEPSEEK_TIMEOUT_SECONDS", "180")
    )
    deepseek_max_retries: int = int(os.getenv("LATTICE_DEEPSEEK_MAX_RETRIES", "1"))
    credential_encryption_key: str = os.getenv(
        "LATTICE_CREDENTIAL_ENCRYPTION_KEY", ""
    )
    allow_custom_model_hosts: bool = _env_bool(
        "LATTICE_ALLOW_CUSTOM_MODEL_HOSTS", False
    )

    @property
    def database_path(self) -> Path:
        return self.data_dir / "latticescholar.db"

    @property
    def policy_path(self) -> Path:
        return PACKAGE_DIR / "data" / "policies.json"

    @property
    def policy_sources_path(self) -> Path:
        return PACKAGE_DIR / "data" / "policy_sources.json"

    @property
    def static_dir(self) -> Path:
        return PACKAGE_DIR / "static"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
