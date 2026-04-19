from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


# ── Environment Presets ──────────────────────────────────────
# Set ENVIRONMENT=development → Groq free tier (default)
# Set ENVIRONMENT=production  → OpenAI / Anthropic paid models
PRESETS: dict[str, dict[str, str]] = {
    "development": {
        "provider": "groq",
        "fast": "llama-3.3-70b-versatile",
        "power": "llama-3.3-70b-versatile",
    },
    "production": {
        "provider": "openai",
        "fast": "gpt-4o-mini",
        "power": "gpt-4o",
    },
}


class Settings(BaseSettings):
    # ── Environment: development | production ─────────────────
    environment: str = "development"

    # ── LLM Provider (groq | openai | anthropic | google | ollama)
    # Leave blank → auto-selected by environment preset
    llm_provider: str = ""

    # ── API Keys (set whichever provider you use) ─────────────
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── Model Tiers ──────────────────────────────────────────
    # Leave blank → auto-selected by environment preset
    llm_model_fast: str = ""
    llm_model_power: str = ""
    llm_default_tier: str = "fast"
    llm_smart_routing: bool = True
    llm_temperature: float = 0.1

    # LLM provider throttling (process-wide; each agent graph step = 1 slot)
    llm_max_requests_per_minute: float = 28.0
    llm_max_concurrent_calls: int = 3
    llm_min_interval_seconds: float = 0.05
    llm_429_max_retries: int = 6
    llm_429_retry_base_seconds: float = 1.5
    llm_429_retry_max_seconds: float = 45.0

    # ── Cost tracking ─────────────────────────────────────────
    cost_tracking_enabled: bool = True
    cost_budget_per_batch: float = 0.0

    # ── Processing ────────────────────────────────────────────
    max_concurrent_tickets: int = 10
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    confidence_threshold: float = 0.6

    # Simulated tool failures (see app/tools/mock_tools.py). Not a real 30s wait —
    # the message mimics an upstream timeout. Set to 0 for stable demos / prod.
    mock_tool_failure_rate: float = 0.05

    # ── Redis ────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300
    cache_ticket_result_ttl: int = 600

    # ── Celery ───────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Database (Supabase Postgres) ────────────────────────────
    database_url: str = ""

    # ── Security ─────────────────────────────────────────────
    api_key: str = ""
    cors_origins: str = "*"
    rate_limit: str = "60/minute"

    # ── Server ────────────────────────────────────────────────
    log_level: str = "INFO"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def resolved_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider
        preset = PRESETS.get(self.environment, PRESETS["development"])
        return preset["provider"]

    @property
    def resolved_model_fast(self) -> str:
        if self.llm_model_fast:
            return self.llm_model_fast
        preset = PRESETS.get(self.environment, PRESETS["development"])
        return preset["fast"]

    @property
    def resolved_model_power(self) -> str:
        if self.llm_model_power:
            return self.llm_model_power
        preset = PRESETS.get(self.environment, PRESETS["development"])
        return preset["power"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
