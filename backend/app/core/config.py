"""Typed application settings, loaded once from the environment (or `.env`)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://clawback:clawback@localhost:5432/clawback"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Document intake
    max_upload_mb: int = 10
    max_pdf_pages: int = 3

    # Workflow
    worker_embedded: bool = True  # run the job worker inside the API process (free-tier hosting)
    worker_poll_seconds: float = 1.0
    sla_sweep_seconds: float = 60.0
    job_max_attempts: int = 3
    case_response_days: int = 20
    retrieval_sla_days: int = 10

    # Evidence produced by models below this confidence routes the case to a human
    auto_resolve_min_confidence: float = 0.80

    # Local ONNX models
    model_dir: Path = BACKEND_ROOT / "models"

    # Optional LLM (any OpenAI-compatible endpoint: HF router, Groq, Gemini, Ollama...)
    llm_base_url: str = "https://router.huggingface.co/v1"
    llm_api_key: str | None = None
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    llm_timeout_seconds: float = 30.0

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres providers (Render, Neon, Supabase) hand out
        postgres:// URLs; SQLAlchemy needs the explicit psycopg 3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
