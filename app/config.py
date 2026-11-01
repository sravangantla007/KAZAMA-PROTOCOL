from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mock_mode: bool = False
    mock_llm: bool = False

    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash"
    llm_api_key: str = ""
    gemini_api_key: str = ""

    search_provider: str = "tavily"
    search_api_key: str = ""
    tavily_api_key: str = ""

    max_sources: int = 12
    max_chars_per_source: int = 16000
    max_prompt_chars: int = 120_000
    max_file_bytes: int = 10_485_760   # 10 MB
    max_files: int = 5
    fetch_timeout_s: int = 10
    max_page_bytes: int = 2_097_152    # 2 MB
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
