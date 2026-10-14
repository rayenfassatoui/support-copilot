from uuid import uuid4

import httpx
import pytest

from app.errors import DomainError
from app.schemas import TicketContext


def test_explicit_content_filter_requires_human_review_without_a_message(provider):
    provider.chat_handler = lambda body, request: httpx.Response(
        200,
        json={"choices": [{"finish_reason": "content_filter", "message": None}]},
    )
    ticket = TicketContext(
        id=uuid4(),
        title="Fictional request",
        description="A synthetic support request.",
        version=1,
    )
    with pytest.raises(DomainError) as raised:
        provider.adapter.analyze(ticket, [])
    assert raised.value.code == "ai_refused"
