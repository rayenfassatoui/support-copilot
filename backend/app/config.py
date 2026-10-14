from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, EmailStr, Field, SecretStr, ValidationError, field_validator, model_validator
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
    neon_auth_base_url: str = ""
    neon_auth_jwks_url: str = ""
    bootstrap_admin_email: EmailStr | None = None
    smtp_host: str = ""
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    smtp_username: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""), repr=False)
    smtp_from: EmailStr = "support@example.com"
    smtp_timeout: float = Field(default=15.0, gt=0, le=60)
    mail_delivery_mode: Literal["mailpit", "smtp"] = "mailpit"
    imap_host: str = ""
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_security: Literal["none", "starttls", "tls"] = "tls"
    imap_username: str = ""
    imap_password: SecretStr = Field(default=SecretStr(""), repr=False)
    imap_folder: str = "INBOX"
    imap_timeout: float = Field(default=15, gt=0, le=60)
    mailbox_poll_seconds: int = Field(default=30, ge=10, le=3600)
    imap_batch_size: int = Field(default=25, ge=1, le=100)
    public_app_url: str = "http://localhost:8080"

    @field_validator("public_app_url")
    @classmethod
    def valid_public_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        url = urlparse(value)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if not url.hostname or url.username or url.password or url.query or url.fragment or url.path or not (
            url.scheme == "https" or (url.scheme == "http" and local)
        ):
            raise ValueError("Public app URL must be an HTTPS origin (HTTP permitted only on loopback).")
        return value

    @field_validator("neon_auth_base_url", "neon_auth_jwks_url")
    @classmethod
    def valid_auth_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value:
            url = urlparse(value)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("Auth URLs must be HTTPS endpoints without credentials or query parameters.")
        return value

    @model_validator(mode="after")
    def consistent_services(self):
        if self.neon_auth_jwks_url:
            base = urlparse(self.neon_auth_base_url)
            jwks = urlparse(self.neon_auth_jwks_url)
            if not base.hostname or base.netloc != jwks.netloc:
                raise ValueError("Auth and JWKS endpoints must use the same trusted origin.")
        if self.mail_delivery_mode == "mailpit" and self.smtp_host not in {"", "mailpit", "localhost", "127.0.0.1", "::1"}:
            raise ValueError("Mailpit mode only permits the local capture server.")
        if self.mail_delivery_mode == "smtp" and self.smtp_security == "none":
            raise ValueError("External SMTP requires TLS.")
        if self.imap_host:
            if self.imap_security == "none" and self.imap_host not in {"mailbox", "localhost", "127.0.0.1", "::1"}:
                raise ValueError("External IMAP requires TLS.")
            if not self.imap_username or not self.imap_password.get_secret_value():
                raise ValueError("IMAP requires a username and password.")
        if any(char in self.imap_folder for char in "\r\n") or not self.imap_folder.strip():
            raise ValueError("Select a valid IMAP folder.")
        return self

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
    except ValidationError as error:
        database_fields = {"database_url", "migration_database_url", "DATABASE_URL", "MIGRATION_DATABASE_URL", "DATABASE_URL_UNPOOLED"}
        if any(issue["loc"] and issue["loc"][0] in database_fields for issue in error.errors(include_input=False)):
            raise RuntimeError(DATABASE_CONFIGURATION_ERROR) from None
        raise RuntimeError("Application service configuration is invalid. Check the server environment.") from None
