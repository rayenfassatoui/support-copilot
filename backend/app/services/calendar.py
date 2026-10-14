from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.errors import DomainError
from app.models import BusinessCalendar


def boundary(day, minute: int, zone: ZoneInfo, *, closing: bool = False) -> datetime:
    wall = datetime.combine(day, time()) + timedelta(minutes=minute)
    # A gap has no real instant: use the first valid wall minute after it.
    # A fold includes the complete repeated opening interval.
    for _ in range(1441):
        candidates = []
        for fold in (0, 1):
            value = wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if value.astimezone(zone).replace(tzinfo=None) == wall:
                candidates.append(value)
        if candidates:
            return max(candidates) if closing else min(candidates)
        wall += timedelta(minutes=1)
    raise DomainError("invalid_business_calendar")


def add_business_minutes(start: datetime, minutes: int, calendar: BusinessCalendar) -> datetime:
    if not calendar.enabled:
        return start + timedelta(minutes=minutes)
    try:
        zone = ZoneInfo(calendar.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainError("invalid_business_calendar") from None
    if not calendar.weekdays or not 0 <= calendar.opens_minute < calendar.closes_minute <= 1440:
        raise DomainError("invalid_business_calendar")
    current = start.astimezone(timezone.utc)
    day = current.astimezone(zone).date()
    holidays = set(calendar.holidays)
    remaining = minutes * 60
    for _ in range(3660):
        if day.weekday() in calendar.weekdays and day.isoformat() not in holidays:
            opens = boundary(day, calendar.opens_minute, zone)
            closes = boundary(day, calendar.closes_minute, zone, closing=True)
            begins = max(current, opens)
            available = max(0, (closes - begins).total_seconds())
            if remaining <= available:
                return begins + timedelta(seconds=remaining)
            remaining -= available
        try:
            day += timedelta(days=1)
        except OverflowError:
            break
    raise DomainError("sla_deadline_out_of_range")
