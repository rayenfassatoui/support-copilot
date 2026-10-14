from alembic import context
from sqlalchemy import create_engine, pool

from app.config import load_settings
from app.models import Base


def run_migrations() -> None:
    settings = load_settings()
    if context.is_offline_mode():
        context.configure(
            url=settings.migration_database_url.get_secret_value(),
            target_metadata=Base.metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(
        settings.migration_database_url.get_secret_value(),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 15},
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    except Exception as error:
        # Avoid raw SQLAlchemy/libpq errors, which can reveal credentials.
        raise RuntimeError(f"Database migration failed ({type(error).__name__}).") from None
    finally:
        engine.dispose()


run_migrations()
