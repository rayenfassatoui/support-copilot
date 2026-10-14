from datetime import date
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas import Priority, RequestModel, Version


class CalendarPatch(RequestModel):
    version: Version
    enabled: bool
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    weekdays: Annotated[list[Annotated[int, Field(strict=True, ge=0, le=6)]], Field(min_length=1, max_length=7)]
    opens_minute: Annotated[int, Field(strict=True, ge=0, le=1439)]
    closes_minute: Annotated[int, Field(strict=True, ge=1, le=1440)]
    holidays: Annotated[list[date], Field(max_length=366)]
    alert_minutes: Annotated[int, Field(strict=True, ge=1, le=10080)]

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA timezone.") from None
        return value

    @model_validator(mode="after")
    def valid_schedule(self):
        if self.closes_minute <= self.opens_minute:
            raise ValueError("Closing time must follow opening time on the same day.")
        if len(set(self.weekdays)) != len(self.weekdays) or len(set(self.holidays)) != len(self.holidays):
            raise ValueError("Weekdays and holidays must not repeat.")
        return self


class CalendarRead(CalendarPatch):
    model_config = ConfigDict(from_attributes=True)


class RuleCreate(RequestModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    enabled: bool = True
    position: Annotated[int, Field(strict=True, ge=0, le=10000)] = 0
    priority: Priority | None = None
    customer_domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253)] | None = None
    subject_contains: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    assignee_id: UUID
    catch_all: bool = False

    @field_validator("customer_domain")
    @classmethod
    def valid_domain(cls, value):
        if value is None:
            return None
        try:
            domain = value.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("Use a valid email domain.") from None
        labels = domain.split(".")
        if len(labels) < 2 or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") or not all(c.isalnum() or c == "-" for c in label) for label in labels):
            raise ValueError("Use a domain such as example.com, without @ or a URL.")
        return domain

    @model_validator(mode="after")
    def explicit_catchall(self):
        empty = self.priority is None and self.customer_domain is None and self.subject_contains is None
        if empty != self.catch_all:
            raise ValueError("Explicitly select Match all for a rule without conditions.")
        return self


class RulePatch(RuleCreate):
    version: Version


class RuleRead(RulePatch):
    id: UUID


class RuleOrderItem(RequestModel):
    id: UUID
    version: Version


class RuleOrder(RequestModel):
    rules: list[RuleOrderItem]
