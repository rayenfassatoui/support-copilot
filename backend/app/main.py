import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.auth import TokenVerifier
from app.config import Settings, load_settings
from app.db import create_database_engine
from app.errors import register_error_handlers
from app.integrations.mail import SMTPMailer
from app.integrations.openrouter import OpenRouterClient
from app.routers import agents, analytics, auth, automation, conversations, feedback, health, knowledge, mailbox, sla, tickets, views
from app.services.members import bootstrap_admin
from app.request_limits import RequestBodyLimit
from app.services.mailbox import poll_mailbox


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_database_engine(settings)
        application.state.sessions = sessionmaker(engine, expire_on_commit=False)
        application.state.settings = settings
        application.state.token_verifier = TokenVerifier(settings)
        application.state.mailer = SMTPMailer(settings)
        stop = asyncio.Event()
        mail_worker = None
        try:
            bootstrap_admin(application.state.sessions, settings)
            with httpx.Client(timeout=httpx.Timeout(45.0, connect=5.0, write=10.0, pool=5.0)) as http:
                application.state.openrouter = OpenRouterClient(http, settings)
                if settings.imap_host:
                    mail_worker = asyncio.create_task(poll_mailbox(application.state.sessions, settings, stop))
                yield
        finally:
            stop.set()
            if mail_worker is not None:
                await mail_worker
            engine.dispose()

    application = FastAPI(title="AI Customer Support Copilot", version="1.0.0", lifespan=lifespan)
    register_error_handlers(application)
    application.add_middleware(RequestBodyLimit)
    application.include_router(auth.router, prefix="/api")
    application.include_router(conversations.router, prefix="/api")
    application.include_router(sla.router, prefix="/api")
    application.include_router(views.router, prefix="/api")
    application.include_router(health.router, prefix="/api")
    application.include_router(agents.router, prefix="/api")
    application.include_router(tickets.router, prefix="/api")
    application.include_router(knowledge.router, prefix="/api")
    application.include_router(mailbox.router, prefix="/api")
    application.include_router(automation.router, prefix="/api")
    application.include_router(analytics.router, prefix="/api")
    application.include_router(feedback.router, prefix="/api")
    return application


app = create_app()
