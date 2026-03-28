"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    default_temperature: float = 0.7
    max_retries: int = 3
    retry_base_delay: float = 1.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
