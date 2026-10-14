from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

DATABASE_CONFIGURATION_ERROR = (
    "Database configuration is missing or invalid. "
    "Set DATABASE_URL and MIGRATION_DATABASE_URL."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", hide_input_in_errors=True, populate_by_name=True, env_ignore_empty=True
    )

    database_url: SecretStr = Field(repr=False)
    migration_database_url: SecretStr = Field(
        repr=False,
        validation_alias=AliasChoices("MIGRATION_DATABASE_URL", "DATABASE_URL_UNPOOLED"),
    )
    openrouter_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    openrouter_chat_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_embedding_model: str = "liquid/lfm-2.5-embedding-350m:free"

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def valid_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            raw = value.get_secret_value()
            if raw.startswith("postgresql://"):
                value = SecretStr("postgresql+psycopg://" + raw[len("postgresql://"):])
            url = make_url(value.get_secret_value())
            valid = (
                url.drivername == "postgresql+psycopg"
                and bool(url.host)
                and bool(url.database)
                and bool(url.username)
                and bool(url.password)
            )
            _ = url.port
        except Exception:
            valid = False
        if not valid:
            raise ValueError(DATABASE_CONFIGURATION_ERROR)
        return value

    @field_validator("openrouter_chat_model", "openrouter_embedding_model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model identifiers must not be blank.")
        return value.strip()


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception:
        raise RuntimeError(DATABASE_CONFIGURATION_ERROR) from None
