from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.schemas import RequestModel, UtcDatetime, Version

Token = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]


class FeedbackLookup(RequestModel):
    token: Token


class FeedbackSubmit(FeedbackLookup):
    rating: Annotated[int, Field(strict=True, ge=1, le=5)]
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""


class FeedbackRequest(RequestModel):
    ticket_version: Version


class TimeMetric(BaseModel):
    completed: int
    outstanding: int
    average_minutes: float | None
    sla_met: int
    sla_breached: int
    sla_pending: int
    sla_percent: float | None


class FeedbackMetric(BaseModel):
    requested: int
    submitted: int
    average_rating: float | None
    satisfied_percent: float | None
    response_percent: float | None


class DailyMetric(BaseModel):
    day: date
    tickets: int
    first_response_minutes: float | None
    resolution_minutes: float | None


class AnalyticsRead(BaseModel):
    start: date
    end: date
    as_of: UtcDatetime
    tickets: int
    first_response: TimeMetric
    resolution: TimeMetric
    feedback: FeedbackMetric
    daily: list[DailyMetric]
