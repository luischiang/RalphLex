"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    model_name: str = "nemotron-3-nano:latest"
    max_tokens: int = 8192
    default_temperature: float = 0.7
    max_retries: int = 3
    retry_base_delay: float = 1.0
    llm_provider: str = "ollama"  # "ollama" or "anthropic"
    ollama_base_url: str = "http://localhost:11434/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
