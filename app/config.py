from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./data/bento.db"
    photos_dir: str = "./data/photos"
    session_secret: str | None = Field(
        default=None, validation_alias="BENTO_SESSION_SECRET"
    )
    cookie_secure: bool = Field(
        default=False, validation_alias="BENTO_COOKIE_SECURE"
    )


settings = Settings()
