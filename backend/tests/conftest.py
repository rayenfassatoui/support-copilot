import json
from dataclasses import dataclass
from threading import Lock
from typing import Callable
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.db import create_database_engine
from app.integrations.openrouter import OpenRouterClient, get_openrouter
from app.models import Agent, CopilotCitation, CopilotRun, KnowledgeChunk, KnowledgeDocument, Member, SavedView, SlaPolicy, Ticket, TicketEvent, TicketMessage
from app.services.members import member_read
from app.services.sla import DEFAULT_POLICIES
from tests.guard_database import assert_test_database_urls, load_guarded_settings

PROVIDER_KEY = "test-only-openrouter-key-never-use-live"
RESET_QUOTE = "Reset links expire after 30 minutes."
RESET_CONTENT = (
    "AcmeCloud fictional demo policy: Password reset.\n"
    "Use Forgot password on the AcmeCloud sign-in page and the account's registered email.\n"
    f"{RESET_QUOTE}\n"
    "Request a fresh link after expiry. Never share passwords or reset links."
)
UNRELATED_CONTENT = (
    "AcmeCloud fictional demo policy: Invoices. "
    "Invoices are available from Settings > Billing > Invoices. "
    "Never request a full card number or CVV."
)
TABLES = (TicketMessage, SavedView, CopilotCitation, CopilotRun, KnowledgeChunk, KnowledgeDocument, TicketEvent, Ticket, Member, Agent)


def unit_vector(axis: int = 0, magnitude: float = 1.0) -> list[float]:
    vector = [0.0] * 1024
    vector[axis] = magnitude
    return vector


def user_payload(body: dict) -> dict:
    messages = [message for message in body["messages"] if message["role"] == "user"]
    assert len(messages) == 1
    return json.loads(messages[0]["content"])


def model_result(body: dict, **overrides) -> dict:
    sources = user_payload(body)["sources"]
    result = {
        "intent": "account",
        "priority": "medium",
        "classification_reason": "The customer needs help accessing their account.",
        "grounded": bool(sources),
        "response_draft": "Please follow the steps in the cited policy." if sources else None,
        "citations": [{"chunk_id": sources[0]["id"], "quote": sources[0]["text"][:180]}] if sources else [],
        "escalation_reasons": [],
    }
    result.update(overrides)
    return result


def chat_envelope(result: dict | str, *, finish_reason: str = "stop") -> dict:
    content = result if isinstance(result, str) else json.dumps(result)
    return {"choices": [{"finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}]}


def database_counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in TABLES}


def reset_database(engine, settings) -> None:
    assert_test_database_urls(settings)
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE TABLE ticket_messages, saved_views, members, copilot_citations, copilot_runs, knowledge_chunks, "
            "knowledge_documents, ticket_events, tickets, agents, sla_policies RESTART IDENTITY"
        ))
        connection.execute(SlaPolicy.__table__.insert(), [
            {"priority": priority, "first_response_minutes": response, "resolution_minutes": resolution, "version": 1}
            for priority, response, resolution in DEFAULT_POLICIES
        ])


@dataclass(frozen=True)
class ProviderCall:
    endpoint: str
    body: dict
    request: httpx.Request


class ProviderTransport:
    def __init__(self, settings):
        self.settings = settings
        self.calls: list[ProviderCall] = []
        self._lock = Lock()
        self.vectors_by_text: dict[str, list[float]] = {}
        self.embedding_handler: Callable[[dict, httpx.Request], httpx.Response] | None = None
        self.chat_handler: Callable[[dict, httpx.Request], httpx.Response] | None = None
        self.http = httpx.Client(
            transport=httpx.MockTransport(self._handle),
            timeout=httpx.Timeout(45.0, connect=5.0, write=10.0, pool=5.0),
        )
        self.adapter = OpenRouterClient(self.http, settings)

    def calls_for(self, endpoint: str) -> list[ProviderCall]:
        with self._lock:
            return [call for call in self.calls if call.endpoint == endpoint]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.removeprefix("/api/v1/")
        body = json.loads(request.content)
        with self._lock:
            self.calls.append(ProviderCall(endpoint, body, request))
        if endpoint == "embeddings":
            if self.embedding_handler is not None:
                return self.embedding_handler(body, request)
            return httpx.Response(200, json={
                "model": "provider-response-alias",
                "data": [
                    {"index": index, "embedding": self.vectors_by_text.get(value, unit_vector())}
                    for index, value in enumerate(body["input"])
                ],
            })
        if endpoint == "chat/completions":
            if self.chat_handler is not None:
                return self.chat_handler(body, request)
            return httpx.Response(200, json=chat_envelope(model_result(body)))
        raise AssertionError(f"Unexpected provider endpoint: {endpoint}")


@pytest.fixture(scope="session")
def guarded_settings():
    return load_guarded_settings()


@pytest.fixture(scope="session")
def database_engine(guarded_settings):
    assert_test_database_urls(guarded_settings)
    engine = create_database_engine(guarded_settings)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert revision, "Run the guarded Alembic migration before the database suite."
            assert connection.execute(text(
                "SELECT count(*) FROM pg_extension WHERE extname = 'vector'"
            )).scalar_one() == 1
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def clean_database(database_engine, guarded_settings):
    reset_database(database_engine, guarded_settings)
    try:
        yield
    finally:
        reset_database(database_engine, guarded_settings)


@pytest.fixture
def settings(guarded_settings):
    settings = guarded_settings.model_copy(deep=True, update={"openrouter_api_key": SecretStr(PROVIDER_KEY)})
    assert_test_database_urls(settings)
    return settings


@pytest.fixture
def sessions(database_engine, clean_database):
    return sessionmaker(database_engine, expire_on_commit=False)


@pytest.fixture
def provider(settings):
    provider = ProviderTransport(settings)
    try:
        yield provider
    finally:
        provider.http.close()


@pytest.fixture
def application(settings, provider, clean_database, member):
    assert_test_database_urls(settings)
    # Importing app.main creates its module-level app; database settings are guarded first.
    from app.main import create_app

    from app.auth import current_member
    application = create_app(settings)
    application.dependency_overrides[get_openrouter] = lambda: provider.adapter
    application.dependency_overrides[current_member] = lambda: member
    return application


@pytest.fixture
def client(application):
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def agents(sessions):
    rows = [
        {"id": str(uuid4()), "name": "Demo Agent", "email": "agent@example.com"},
        {"id": str(uuid4()), "name": "Rayen Fassatoui", "email": "rayen@example.com"},
    ]
    from uuid import UUID

    with sessions.begin() as session:
        session.add_all([Agent(id=UUID(row["id"]), name=row["name"], email=row["email"]) for row in rows])
    return rows


@pytest.fixture
def member(agents, sessions):
    from uuid import UUID
    with sessions.begin() as session:
        account = Member(agent_id=UUID(agents[0]["id"]), name=agents[0]["name"], email=agents[0]["email"],
                         role="admin", active=True, version=1)
        session.add(account)
        session.flush()
        return member_read(account)


@pytest.fixture
def ticket_factory(client):
    def create(**overrides):
        payload = {
            "title": "Cannot reset my password",
            "description": "I cannot sign in to my AcmeCloud account. How do I reset my password?",
            "customer_email": "customer@example.com",
        }
        payload.update(overrides)
        response = client.post("/api/tickets", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return create


@pytest.fixture
def document_factory(client):
    def create(**overrides):
        payload = {"title": "Password reset", "content": RESET_CONTENT, "source_url": None}
        payload.update(overrides)
        response = client.post("/api/knowledge", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return create
