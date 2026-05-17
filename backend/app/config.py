from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Storage
    database_url: str = Field(..., min_length=1)
    es_url: str = Field(..., min_length=1)
    redis_url: str = Field(..., min_length=1)

    # Auth
    jwt_secret: SecretStr = Field(..., min_length=32)
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604_800

    # LLM (Phase 4, optional)
    dashscope_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None

    # Knowledge Pipeline (Phase 3)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"
    chunk_size: int = 512
    chunk_overlap: int = 128
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_k: int = 5
    vision_enabled: bool = False
    vision_model: str = "qwen-vl-max"
    vision_max_images_per_doc: int = 20

    # CORS
    cors_origins: list[str] = ["*"]

    # Runtime
    data_dir: str = "data"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    environment: Literal["dev", "test", "prod"] = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
