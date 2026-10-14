import os
from pathlib import Path
import subprocess
import sys

from pydantic import SecretStr
import pytest

from app.config import Settings
from tests.conftest import reset_database
from tests.guard_database import REFUSAL_MESSAGE, assert_test_database_urls

LOCAL_URL = "postgresql+psycopg://copilot_test:copilot_test@db-test:5432/copilot_test"
REMOTE_URL = "postgresql+psycopg://cloud_owner:private-password@ep-demo-pooler.neon.tech/neondb?sslmode=require"


def unchecked_settings(runtime=LOCAL_URL, migration=LOCAL_URL):
    fields = {}
    if runtime is not None:
        fields["database_url"] = SecretStr(runtime)
    if migration is not None:
        fields["migration_database_url"] = SecretStr(migration)
    return Settings.model_construct(**fields)


def guard_environment(**values):
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("DATABASE_URL", "MIGRATION_DATABASE_URL", "OPENROUTER_"))
    }
    environment.update(values)
    backend = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, (backend, environment.get("PYTHONPATH"))))
    return environment


def test_valid_disposable_targets_pass_without_connecting():
    settings = Settings(database_url=LOCAL_URL, migration_database_url=LOCAL_URL, _env_file=None)
    assert_test_database_urls(settings)


@pytest.mark.parametrize("field", ["database_url", "migration_database_url"])
@pytest.mark.parametrize("target", [
    REMOTE_URL,
    "postgresql+psycopg://user:private-password@db-test/another_database",
    "postgresql+psycopg://user:private-password@db-test.evil/copilot_test",
    "postgresql+psycopg://user:private-password@localhost/copilot_test",
    "postgresql+psycopg://user:private-password@DB-TEST/copilot_test",
    "postgresql+psycopg://user:private-password@db-test/copilot_test_extra",
    "postgresql+psycopg://user:private-password@db-test:invalid/copilot_test",
    LOCAL_URL + "?host=ep-demo-pooler.neon.tech",
    LOCAL_URL + "?hostaddr=203.0.113.7",
    LOCAL_URL + "?dbname=neondb",
    LOCAL_URL + "?service=remote_database",
    "sqlite:///copilot_test",
    "private-password-not-a-url",
    "",
    None,
])
def test_each_url_is_guarded_and_errors_do_not_disclose_targets(field, target):
    values = {"runtime": LOCAL_URL, "migration": LOCAL_URL}
    values["runtime" if field == "database_url" else "migration"] = target
    with pytest.raises(RuntimeError) as raised:
        assert_test_database_urls(unchecked_settings(**values))
    assert str(raised.value) == REFUSAL_MESSAGE
    assert "private-password" not in str(raised.value)
    assert raised.value.__suppress_context__ is True


@pytest.mark.parametrize("runtime,migration", [(REMOTE_URL, LOCAL_URL), (LOCAL_URL, REMOTE_URL)])
def test_remote_target_is_rejected_before_reset_opens_a_connection(runtime, migration):
    class NeverConnect:
        reached = False

        def begin(self):
            self.reached = True
            raise AssertionError("A connection must not be opened for a rejected target.")

    engine = NeverConnect()
    with pytest.raises(RuntimeError) as raised:
        reset_database(engine, unchecked_settings(runtime, migration))
    assert str(raised.value) == REFUSAL_MESSAGE
    assert engine.reached is False


@pytest.mark.parametrize("values", [
    {},
    {"DATABASE_URL": LOCAL_URL},
    {"MIGRATION_DATABASE_URL": LOCAL_URL},
    {"DATABASE_URL": "", "MIGRATION_DATABASE_URL": LOCAL_URL},
    {"DATABASE_URL": "not-a-url-private-password", "MIGRATION_DATABASE_URL": LOCAL_URL},
    {"DATABASE_URL": LOCAL_URL, "MIGRATION_DATABASE_URL": "not-a-url-private-password"},
    {"DATABASE_URL": REMOTE_URL, "MIGRATION_DATABASE_URL": LOCAL_URL},
    {"DATABASE_URL": LOCAL_URL, "MIGRATION_DATABASE_URL": REMOTE_URL},
    {"DATABASE_URL": LOCAL_URL, "MIGRATION_DATABASE_URL": "", "DATABASE_URL_UNPOOLED": REMOTE_URL},
])
def test_guard_cli_fails_closed_without_a_database(values, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "tests.guard_database"],
        cwd=tmp_path,
        env=guard_environment(**values),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == REFUSAL_MESSAGE
    assert "private-password" not in result.stderr
    assert "neon.tech" not in result.stderr


@pytest.mark.parametrize("configured", [False, True])
def test_guard_cli_ignores_dotenv_and_never_requires_database_connectivity(configured, tmp_path):
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={REMOTE_URL}\nMIGRATION_DATABASE_URL={REMOTE_URL}\n",
        encoding="utf-8",
    )
    values = {"DATABASE_URL": LOCAL_URL, "MIGRATION_DATABASE_URL": LOCAL_URL} if configured else {}
    result = subprocess.run(
        [sys.executable, "-m", "tests.guard_database"],
        cwd=tmp_path,
        env=guard_environment(**values),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if configured:
        assert result.returncode == 0
        assert result.stdout == result.stderr == ""
    else:
        assert result.returncode != 0
        assert result.stderr.strip() == REFUSAL_MESSAGE
