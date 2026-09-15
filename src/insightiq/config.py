from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INSIGHTIQ_", extra="ignore")

    agent_mode: str = Field(default="deterministic", pattern="^(deterministic|openai)$")
    openai_model: str = "gpt-5.6-sol"
    max_steps: int = Field(default=15, ge=1, le=50)
    max_tool_calls: int = Field(default=12, ge=1, le=50)
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
