from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def create_database_engine(settings: Settings):
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
        hide_parameters=True,
    )


def get_sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.sessions
