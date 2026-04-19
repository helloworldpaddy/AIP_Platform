"""
Centralized configuration.

Loading order (later sources override earlier ones):
    1. Defaults defined on the model
    2. `config.yaml` at the repo root (if present)
    3. Environment variables (via pydantic-settings / .env)

All components import `get_settings()` to access a cached Settings instance.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_PATH = _REPO_ROOT / "config.yaml"
_ENV_PATH = _REPO_ROOT / ".env"


_BASE_CONFIG = SettingsConfigDict(
    extra="ignore",
    env_file=str(_ENV_PATH),
    populate_by_name=True,
)


class GeminiSettings(BaseSettings):
    api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    use_vertex: bool = Field(default=False, alias="GOOGLE_GENAI_USE_VERTEXAI")
    project: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT")
    location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")

    embedding_model: str = Field(default="text-embedding-004", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM")
    generation_model: str = Field(default="gemini-2.0-flash", alias="GENERATION_MODEL")
    request_timeout_seconds: int = 30
    embedding_batch_size: int = 100

    model_config = _BASE_CONFIG


class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    name: str = Field(default="ragdb", alias="POSTGRES_DB")
    user: str = Field(default="raguser", alias="POSTGRES_USER")
    password: SecretStr = Field(default=SecretStr("ragpass"), alias="POSTGRES_PASSWORD")
    pool_min: int = Field(default=2, alias="POSTGRES_POOL_MIN")
    pool_max: int = Field(default=10, alias="POSTGRES_POOL_MAX")
    statement_timeout_ms: int = 15000

    model_config = _BASE_CONFIG

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class IngestionSettings(BaseSettings):
    chunk_size: int = Field(default=800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=100, alias="CHUNK_OVERLAP")
    supported_extensions: list[str] = [".pdf", ".docx", ".txt", ".md"]
    max_file_mb: int = 50

    model_config = _BASE_CONFIG


class RetrievalSettings(BaseSettings):
    top_k: int = Field(default=5, alias="TOP_K")
    ivfflat_lists: int = Field(default=100, alias="IVFFLAT_LISTS")
    ivfflat_probes: int = 10
    hybrid_search: bool = Field(default=True, alias="HYBRID_SEARCH")
    hybrid_vector_weight: float = 0.7
    hybrid_bm25_weight: float = 0.3
    enable_rerank: bool = Field(default=False, alias="ENABLE_RERANK")
    rerank_top_n: int = 20

    model_config = _BASE_CONFIG


class CacheSettings(BaseSettings):
    enabled: bool = Field(default=False, alias="CACHE_ENABLED")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    ttl_seconds: int = Field(default=3600, alias="CACHE_TTL_SECONDS")

    model_config = _BASE_CONFIG


class AMLSettings(BaseSettings):
    enabled: bool = True
    boost_keywords: list[str] = Field(default_factory=list)
    high_risk_jurisdictions: list[str] = Field(default_factory=list)
    risk_weights: dict[str, float] = Field(
        default_factory=lambda: {"vector": 0.6, "bm25": 0.2, "entity": 0.1, "keyword": 0.1}
    )


class ObservabilitySettings(BaseSettings):
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    service_name: str = Field(default="adk-rag-postgres", alias="OTEL_SERVICE_NAME")
    otlp_endpoint: str | None = Field(default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    model_config = _BASE_CONFIG


def _yaml_for(cls: type[BaseSettings], section: dict[str, Any]) -> dict[str, Any]:
    """
    Return only the YAML entries whose corresponding env alias is NOT set.

    pydantic-settings treats init kwargs as the highest-priority source, so
    naively passing all YAML values would make YAML beat env. We pre-filter
    so env (and .env) always wins when an operator has explicitly set a
    variable — which is the precedence documented in the README.
    """
    env_aliases: set[str] = set()
    for field in cls.model_fields.values():
        if field.alias:
            env_aliases.add(field.alias)
    return {
        k: v for k, v in section.items()
        # Drop YAML values if the field's env alias is set.
        if not any(
            field.alias in os.environ and _matches(k, field, cls)
            for field in cls.model_fields.values()
            if field.alias
        )
    }


def _matches(yaml_key: str, field, cls: type[BaseSettings]) -> bool:
    # A YAML key targets a field if it equals either the field name or alias.
    for name, f in cls.model_fields.items():
        if f is field:
            return yaml_key == name or yaml_key == f.alias
    return False


class Settings:
    """Aggregate settings loaded from YAML + env."""

    def __init__(self, yaml_data: dict[str, Any] | None = None) -> None:
        yaml_data = yaml_data or {}
        self.gemini = GeminiSettings(**_yaml_for(GeminiSettings, yaml_data.get("gemini", {})))
        self.database = DatabaseSettings(**_yaml_for(DatabaseSettings, yaml_data.get("database", {})))
        self.ingestion = IngestionSettings(**_yaml_for(IngestionSettings, yaml_data.get("ingestion", {})))
        self.retrieval = RetrievalSettings(**_yaml_for(RetrievalSettings, yaml_data.get("retrieval", {})))
        self.cache = CacheSettings(**_yaml_for(CacheSettings, yaml_data.get("cache", {})))
        self.aml = AMLSettings(**_yaml_for(AMLSettings, yaml_data.get("aml", {})))
        self.observability = ObservabilitySettings(
            **_yaml_for(ObservabilitySettings, yaml_data.get("observability", {}))
        )


def _load_yaml() -> dict[str, Any]:
    path = Path(os.environ.get("RAG_CONFIG_PATH", _CONFIG_PATH))
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance."""
    return Settings(_load_yaml())
