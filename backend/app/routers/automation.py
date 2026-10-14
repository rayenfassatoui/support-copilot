from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, sessionmaker

from app.auth import current_member, require_admin
from app.automation_schemas import CalendarPatch, CalendarRead, RuleCreate, RuleOrder, RulePatch, RuleRead
from app.db import get_sessions
from app.schemas import MemberRead
from app.services import automation

router = APIRouter(prefix="/automation", tags=["automation"])
Sessions = Annotated[sessionmaker[Session], Depends(get_sessions)]
Admin = Annotated[MemberRead, Depends(require_admin)]
Actor = Annotated[MemberRead, Depends(current_member)]


@router.get("/calendar", response_model=CalendarRead)
def calendar(sessions: Sessions, admin: Admin):
    return automation.read_calendar(sessions)


@router.patch("/calendar", response_model=CalendarRead)
def patch_calendar(payload: CalendarPatch, sessions: Sessions, admin: Admin):
    return automation.patch_calendar(sessions, payload)


@router.get("/rules", response_model=list[RuleRead])
def rules(sessions: Sessions, admin: Admin):
    return automation.list_rules(sessions)


@router.post("/rules", response_model=RuleRead, status_code=201)
def create_rule(payload: RuleCreate, sessions: Sessions, admin: Admin):
    return automation.create_rule(sessions, payload)


@router.put("/rules/order", response_model=list[RuleRead])
def order_rules(payload: RuleOrder, sessions: Sessions, admin: Admin):
    return automation.order_rules(sessions, payload)


@router.patch("/rules/{rule_id}", response_model=RuleRead)
def patch_rule(rule_id: UUID, payload: RulePatch, sessions: Sessions, admin: Admin):
    return automation.patch_rule(sessions, rule_id, payload)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: UUID, sessions: Sessions, admin: Admin, version: Annotated[int, Query(ge=1)]):
    automation.delete_rule(sessions, rule_id, version)
    return Response(status_code=204)


@router.get("/sla-alerts")
def sla_alerts(sessions: Sessions, actor: Actor, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    return automation.sla_alerts(sessions, limit)
