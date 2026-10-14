import sys

from sqlalchemy.engine import make_url

from app.config import Settings

REFUSAL_MESSAGE = "Refusing to run tests against a non-test database."


def assert_test_database_urls(settings: Settings) -> None:
    try:
        for field in ("database_url", "migration_database_url"):
            url = make_url(getattr(settings, field).get_secret_value())
            if (
                url.drivername != "postgresql+psycopg"
                or url.host != "db-test"
                or url.database != "copilot_test"
                or {"host", "hostaddr", "dbname", "database", "service", "servicefile"}.intersection(url.query)
            ):
                raise ValueError
            _ = url.port
    except Exception:
        raise RuntimeError(REFUSAL_MESSAGE) from None


def load_guarded_settings() -> Settings:
    try:
        settings = Settings(_env_file=None)
    except Exception:
        raise RuntimeError(REFUSAL_MESSAGE) from None
    assert_test_database_urls(settings)
    return settings


def main() -> int:
    try:
        load_guarded_settings()
    except RuntimeError:
        print(REFUSAL_MESSAGE, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
