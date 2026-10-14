from datetime import datetime
from uuid import UUID

from app.schemas import TicketEventRead


def test_public_timestamps_normalize_offset_and_calendar_date_to_utc():
    record = TicketEventRead(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        ticket_id=UUID("00000000-0000-0000-0000-000000000002"),
        ticket_version=1,
        changes={},
        created_at=datetime.fromisoformat("2026-01-02T01:00:00+02:00"),
    )
    assert record.model_dump(mode="json")["created_at"] == "2026-01-01T23:00:00Z"
