from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    leads_chat_id: int
    admin_ids: Annotated[list[int], NoDecode] = []
    database_url: str
    api_key: str
    public_base_url: str = "http://localhost:8000"
    media_dir: Path = Path("media")
    tz: str = "Europe/Kyiv"
    contact_phone: str = "+38 (097) 011-33-61"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value):
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
