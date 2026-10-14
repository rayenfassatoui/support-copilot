from array import array
from math import isfinite
import logging
import json

import httpx
from fastapi import Request
from pydantic import ValidationError

from app.config import Settings
from app.errors import DomainError
from app.schemas import ModelAnalysis, RetrievedChunk, TicketContext
from app.services.copilot import SYSTEM_POLICY, validate_citations
from app.tokenization import EMBEDDING_TOKEN_LIMIT, token_count

logger = logging.getLogger("copilot")
BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    def __init__(self, http: httpx.Client, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    def require_key(self) -> None:
        if not self.settings.openrouter_api_key.get_secret_value().strip():
            raise DomainError("ai_not_configured")

    def _post(self, endpoint: str, body: dict) -> dict:
        self.require_key()
        try:
            response = self.http.post(
                f"{BASE_URL}/{endpoint}", json=body,
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key.get_secret_value()}",
                         "Content-Type": "application/json"},
            )
        except httpx.TimeoutException:
            logger.warning("provider category=timeout")
            raise DomainError("ai_timeout") from None
        except httpx.RequestError:
            logger.warning("provider category=network")
            raise DomainError("ai_unavailable") from None
        if not 200 <= response.status_code < 300:
            logger.warning("provider category=http status=%d", response.status_code)
            raise DomainError("ai_unavailable")
        try:
            payload = response.json()
        except ValueError:
            raise DomainError("ai_invalid_response") from None
        if not isinstance(payload, dict):
            raise DomainError("ai_invalid_response")
        if payload.get("error") is not None:
            logger.warning("provider category=upstream_error status=%d", response.status_code)
            raise DomainError("ai_unavailable")
        return payload

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.require_key()
        # Count native Liquid tokens, including the prefix and special tokens, before any batch.
        for text in texts:
            if not isinstance(text, str) or not text.strip():
                raise DomainError("ai_invalid_response")
            if token_count(text) > EMBEDDING_TOKEN_LIMIT:
                raise DomainError("ai_input_too_long")
        vectors = []
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            payload = self._post("embeddings", {
                "model": self.settings.openrouter_embedding_model, "input": batch,
                "encoding_format": "float", "provider": {"only": ["liquid"], "allow_fallbacks": False},
            })
            data = payload.get("data")
            if not isinstance(data, list) or len(data) != len(batch):
                raise DomainError("ai_invalid_response")
            by_index = {}
            for item in data:
                if not isinstance(item, dict):
                    raise DomainError("ai_invalid_response")
                index = item.get("index")
                if "index" not in item and len(batch) == 1:
                    index = 0
                if type(index) is not int or not 0 <= index < len(batch) or index in by_index:
                    raise DomainError("ai_invalid_response")
                raw = item.get("embedding")
                if not isinstance(raw, list) or len(raw) != 1024 or any(type(value) not in (int, float) for value in raw):
                    raise DomainError("ai_invalid_response")
                try:
                    vector = array("f", raw)
                    if not all(isfinite(value) for value in vector) or not any(vector):
                        raise ValueError("Invalid vector")
                except (ValueError, TypeError, OverflowError):
                    raise DomainError("ai_invalid_response") from None
                by_index[index] = vector.tolist()
            vectors.extend(by_index[index] for index in range(len(batch)))
        return vectors

    def analyze(self, ticket: TicketContext, chunks: list[RetrievedChunk]) -> ModelAnalysis:
        payload = self._post("chat/completions", {
            "model": self.settings.openrouter_chat_model,
            "stream": False, "temperature": 0.2, "max_tokens": 1800,
            "provider": {"only": ["nvidia"], "require_parameters": True, "allow_fallbacks": False},
            "reasoning": {"enabled": False, "exclude": True},
            "messages": [
                {"role": "system", "content": SYSTEM_POLICY + "\nJSON Schema:\n" + json.dumps(ModelAnalysis.model_json_schema())},
                {"role": "user", "content": json.dumps({
                    "ticket": {"title": ticket.title, "description": ticket.description},
                    "sources": [{"id": str(chunk.id), "title": chunk.title, "text": chunk.text} for chunk in chunks],
                }, ensure_ascii=False)},
            ],
        })
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise DomainError("ai_invalid_response")
        choice = choices[0]
        if choice.get("error") is not None:
            raise DomainError("ai_unavailable")
        if choice.get("finish_reason") == "content_filter":
            raise DomainError("ai_refused")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise DomainError("ai_invalid_response")
        if message.get("refusal"):
            raise DomainError("ai_refused")
        content = message.get("content")
        if choice.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip():
            raise DomainError("ai_invalid_response")
        try:
            result = ModelAnalysis.model_validate_json(content)
        except (ValidationError, ValueError):
            raise DomainError("ai_invalid_response") from None
        validate_citations(result, chunks)
        return result


def get_openrouter(request: Request) -> OpenRouterClient:
    return request.app.state.openrouter
