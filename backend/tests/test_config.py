from pydantic import ValidationError
import pytest

from app.config import DATABASE_CONFIGURATION_ERROR, Settings, load_settings
from tests.test_guard import LOCAL_URL


@pytest.fixture
def database_environment(monkeypatch):
    import os

    for key in list(os.environ):
        if key.upper() in {"DATABASE_URL", "MIGRATION_DATABASE_URL", "DATABASE_URL_UNPOOLED"}:
            monkeypatch.delenv(key)
    return monkeypatch


@pytest.mark.parametrize("runtime,migration", [
    (None, None),
    (LOCAL_URL, None),
    (None, LOCAL_URL),
    ("", LOCAL_URL),
    (LOCAL_URL, ""),
    ("not-a-url-secret-value", LOCAL_URL),
    (LOCAL_URL, "not-a-url-secret-value"),
    ("postgresql+asyncpg://user:private-password@db-test/copilot_test", LOCAL_URL),
    (LOCAL_URL, "postgresql+psycopg://user:private-password@db-test:invalid/copilot_test"),
])
def test_missing_or_invalid_configuration_has_a_safe_startup_error(database_environment, runtime, migration):
    if runtime is not None:
        database_environment.setenv("DATABASE_URL", runtime)
    if migration is not None:
        database_environment.setenv("MIGRATION_DATABASE_URL", migration)
    with pytest.raises(RuntimeError) as raised:
        load_settings()
    assert str(raised.value) == DATABASE_CONFIGURATION_ERROR
    assert "private-password" not in str(raised.value)
    assert "secret-value" not in str(raised.value)
    assert raised.value.__suppress_context__ is True


def test_direct_validation_and_settings_repr_hide_secrets():
    invalid = "postgresql+psycopg://owner:private-password@db-test:invalid/copilot_test"
    with pytest.raises(ValidationError) as raised:
        Settings(database_url=invalid, migration_database_url=LOCAL_URL, _env_file=None)
    assert "private-password" not in str(raised.value)
    settings = Settings(
        database_url=LOCAL_URL,
        migration_database_url=LOCAL_URL,
        openrouter_api_key="private-provider-key",
        _env_file=None,
    )
    assert "private-provider-key" not in repr(settings)
    assert LOCAL_URL not in repr(settings)
