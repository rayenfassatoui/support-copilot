from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, cast, extract, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics_schemas import AnalyticsRead, DailyMetric, FeedbackMetric, TimeMetric
from app.models import CustomerFeedback, Ticket


def metric(row, prefix: str, total: int) -> TimeMetric:
    completed, eligible, met = row[f"{prefix}_completed"], row[f"{prefix}_eligible"], row[f"{prefix}_met"]
    average = row[f"{prefix}_average"]
    return TimeMetric(completed=completed, outstanding=total - completed,
        average_minutes=float(average) if average is not None else None,
        sla_met=met, sla_breached=eligible - met, sla_pending=total - eligible,
        sla_percent=100 * met / eligible if eligible else None)


def report(sessions: sessionmaker[Session], start: date, end: date, now: datetime | None = None) -> AnalyticsRead:
    now = now or datetime.now(timezone.utc)
    begin, finish = datetime.combine(start, time(), timezone.utc), datetime.combine(end, time(), timezone.utc)
    cohort = (Ticket.created_at >= begin, Ticket.created_at < finish)
    columns = [func.count(Ticket.id).label("total")]
    for prefix, completed, due in (("response", Ticket.first_response_at, Ticket.first_response_due_at),
                                   ("resolution", Ticket.resolved_at, Ticket.resolution_due_at)):
        columns.extend([
            func.count().filter(completed.is_not(None)).label(f"{prefix}_completed"),
            func.avg(extract("epoch", completed - Ticket.created_at) / 60).label(f"{prefix}_average"),
            func.count().filter(or_(completed.is_not(None), due < now)).label(f"{prefix}_eligible"),
            func.count().filter(completed.is_not(None), completed <= due).label(f"{prefix}_met"),
        ])
    with sessions() as session:
        row = session.execute(select(*columns).where(*cohort)).mappings().one()
        day = cast(func.timezone("UTC", Ticket.created_at), Date)
        daily = session.execute(select(day.label("day"), func.count().label("tickets"),
            func.avg(extract("epoch", Ticket.first_response_at - Ticket.created_at) / 60).label("response"),
            func.avg(extract("epoch", Ticket.resolved_at - Ticket.created_at) / 60).label("resolution"))
            .where(*cohort).group_by(day).order_by(day)).mappings().all()
        feedback = session.execute(select(func.count().label("requested"),
            func.count(CustomerFeedback.rating).label("submitted"), func.avg(CustomerFeedback.rating).label("average"),
            func.count().filter(CustomerFeedback.rating >= 4).label("satisfied"))
            .where(CustomerFeedback.created_at >= begin, CustomerFeedback.created_at < finish)).mappings().one()
    by_day = {item["day"]: item for item in daily}
    days = []
    current = start
    while current < end:
        item = by_day.get(current)
        days.append(DailyMetric(day=current, tickets=item["tickets"] if item else 0,
            first_response_minutes=float(item["response"]) if item and item["response"] is not None else None,
            resolution_minutes=float(item["resolution"]) if item and item["resolution"] is not None else None))
        current += timedelta(days=1)
    submitted, requested = feedback["submitted"], feedback["requested"]
    return AnalyticsRead(start=start, end=end, as_of=now, tickets=row["total"],
        first_response=metric(row, "response", row["total"]), resolution=metric(row, "resolution", row["total"]),
        feedback=FeedbackMetric(requested=requested, submitted=submitted,
            average_rating=float(feedback["average"]) if feedback["average"] is not None else None,
            satisfied_percent=100 * feedback["satisfied"] / submitted if submitted else None,
            response_percent=100 * submitted / requested if requested else None), daily=days)
