from datetime import timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AnyHttpUrl, AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator


class Status(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    escalated = "escalated"


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=10000)]
Version = Annotated[int, Field(strict=True, ge=1)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(timezone.utc))]


class TicketCreate(RequestModel):
    title: Title
    description: Description
    customer_email: EmailStr
    assignee_id: UUID | None = None



class TicketPatch(RequestModel):
    version: Version
    title: Title | None = None
    description: Description | None = None
    customer_email: EmailStr | None = None
    status: Status | None = None
    assignee_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def valid_edit(cls, data):
        if isinstance(data, dict):
            editable = {"title", "description", "customer_email", "status", "assignee_id"}
            if not editable.intersection(data):
                raise ValueError("Provide at least one editable field.")
            if any(data[key] is None for key in editable.difference({"assignee_id"}).intersection(data)):
                raise ValueError("Only assignee_id may be null.")
        return data


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: EmailStr


class TicketFields(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str
    customer_email: EmailStr
    status: Status
    assignee_id: UUID | None
    version: int
    created_at: UtcDatetime
    updated_at: UtcDatetime
    assignee: AgentRead | None


Intent = Literal["billing", "technical", "account", "cancellation", "security", "other"]
Priority = Literal["low", "medium", "high", "urgent"]


class EscalationReason(str, Enum):
    insufficient_knowledge = "insufficient_knowledge"
    security_or_privacy = "security_or_privacy"
    legal_or_compliance = "legal_or_compliance"
    human_requested = "human_requested"
    urgent_impact = "urgent_impact"
    policy_requires_review = "policy_requires_review"


class ModelCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    chunk_id: str
    quote: str

    @field_validator("chunk_id")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("quote")
    @classmethod
    def valid_quote(cls, value: str) -> str:
        if not value.strip() or len(value) > 600:
            raise ValueError("Quote must be nonblank and at most 600 characters.")
        return value


class ModelAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: Intent
    priority: Priority
    classification_reason: str
    grounded: bool
    response_draft: str | None
    citations: list[ModelCitation]
    escalation_reasons: list[EscalationReason]

    @model_validator(mode="after")
    def valid_analysis(self):
        if not self.classification_reason.strip() or len(self.classification_reason) > 500:
            raise ValueError("Classification reason must be nonblank and at most 500 characters.")
        if len(set(self.escalation_reasons)) != len(self.escalation_reasons):
            raise ValueError("Escalation reasons must be unique.")
        if len({citation.chunk_id for citation in self.citations}) != len(self.citations):
            raise ValueError("Cited chunks must be unique.")
        if self.grounded:
            if self.response_draft is None or not self.response_draft.strip() or len(self.response_draft) > 6000:
                raise ValueError("Grounded draft must be nonblank and at most 6000 characters.")
            if not 1 <= len(self.citations) <= 5:
                raise ValueError("A grounded draft requires one to five citations.")
        elif self.response_draft is not None or self.citations:
            raise ValueError("Ungrounded results must have no draft or citations.")
        return self


class TicketContext(BaseModel):
    id: UUID
    title: str
    description: str
    version: int


class RetrievedChunk(BaseModel):
    id: UUID
    document_id: UUID
    title: str
    text: str
    source_url: str | None


class CitationRead(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    quote: str
    source_url: str | None


class EscalationRead(BaseModel):
    recommended: bool
    reasons: list[EscalationReason]


class CopilotRunRead(BaseModel):
    id: UUID
    ticket_id: UUID
    ticket_version: int
    model: str
    intent: Intent
    priority: Priority
    classification_reason: str
    grounded: bool
    response_draft: str | None
    citations: list[CitationRead]
    escalation: EscalationRead
    created_at: UtcDatetime


class AnalysisSummary(BaseModel):
    id: UUID
    intent: Intent
    priority: Priority
    escalation_recommended: bool


class AnalyzeRequest(RequestModel):
    version: Version


class TicketRead(TicketFields):
    latest_analysis: CopilotRunRead | None
    analysis_stale: bool


class TicketListItem(TicketFields):
    latest_analysis: AnalysisSummary | None
    analysis_stale: bool


class TicketPage(BaseModel):
    items: list[TicketListItem]
    total: int
    limit: int
    offset: int


class TicketEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ticket_id: UUID
    ticket_version: int
    changes: dict
    created_at: UtcDatetime


class KnowledgeCreate(RequestModel):
    title: Title
    content: Annotated[str, StringConstraints(min_length=50, max_length=20000)]
    source_url: AnyHttpUrl | None = None

    @field_validator("content", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return value.replace("\r\n", "\n").strip() if isinstance(value, str) else value


class KnowledgeSummary(BaseModel):
    id: UUID
    title: str
    source_url: str | None
    created_at: UtcDatetime
    chunk_count: int


class KnowledgeRead(KnowledgeSummary):
    content: str
