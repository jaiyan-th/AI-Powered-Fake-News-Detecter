"""
Application Configuration using Pydantic Settings
"""

from pathlib import Path
from secrets import token_urlsafe
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # App Info
    APP_NAME: str = "AI News Verification System"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    PRODUCTION: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    DATABASE_DIR: Path = PROJECT_ROOT / "database"
    CORS_ORIGINS: list[str] = Field(default_factory=list)

    # API Keys
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API Key for LLM inference")
    NEWS_API_KEY: Optional[str] = Field(default=None, description="NewsAPI Key for real-time news retrieval")
    SERPAPI_KEY: Optional[str] = Field(default=None, description="SerpAPI Key for Google News search")


    # Embeddings
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-small-en-v1.5", description="FastEmbed model identifier")
    EMBEDDING_DIM: int = Field(default=384, description="Embedding vector dimensions")

    # Groq LLM Configuration
    GROQ_MODEL: str = Field(default="openai/gpt-oss-120b", description="Primary Groq model for speed and accuracy")
    GROQ_REASONING_MODEL: str = Field(default="openai/gpt-oss-20b", description="Secondary Groq model")
    GROQ_TIMEOUT_SECONDS: int = 25
    GROQ_MAX_RETRIES: int = 3

    # Search & Retrieval Limits
    NEWS_API_LIMIT: int = 15
    SERPAPI_LIMIT: int = 15
    REQUEST_TIMEOUT_SECONDS: int = 6
    TOP_K_EVIDENCE: int = 6
    EVIDENCE_FRESHNESS_DAYS: int = 60  # Prioritize within this window for breaking news

    # Authentication & Security
    JWT_SECRET_KEY: str = Field(default_factory=lambda: token_urlsafe(48), description="HMAC secret key for JWT")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days session
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_VERIFY_PER_MINUTE: int = 20
    RATE_LIMIT_AUTH_PER_MINUTE: int = 30
    TRUST_PROXY_HEADERS: bool = False

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.PRODUCTION:
            if self.DEBUG:
                raise ValueError("DEBUG must be disabled in production.")
            if "JWT_SECRET_KEY" not in self.model_fields_set or len(self.JWT_SECRET_KEY.strip().encode()) < 32:
                raise ValueError("Production requires an explicit JWT_SECRET_KEY of at least 32 bytes.")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("Production CORS origins must be explicit.")
        return self


settings = Settings()
