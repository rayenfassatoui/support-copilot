import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

logger = logging.getLogger("copilot")

ERRORS = {
    "not_found": (404, "Resource not found."),
    "invalid_assignee": (422, "Select an existing agent."),
    "ticket_conflict": (409, "This ticket changed. Reload it before continuing."),
    "duplicate_document": (409, "This document is already indexed."),
    "ai_input_too_long": (422, "This text is too long for AI analysis. Shorten it and try again."),
    "ai_not_configured": (503, "Configure OPENROUTER_API_KEY on the server to use AI."),
    "embedding_model_mismatch": (503, "The configured embedding model does not match the indexed knowledge base."),
    "ai_timeout": (504, "The AI request timed out. No changes were saved."),
    "ai_unavailable": (503, "The AI service is unavailable. Check server configuration or try again later."),
    "ai_refused": (502, "The AI declined this request. Review it manually."),
    "ai_invalid_response": (502, "The AI returned an unusable response. No changes were saved."),
    "database_unavailable": (503, "The database is temporarily unavailable."),
    "internal_error": (500, "An unexpected error occurred."),
    "authentication_required": (401, "Sign in to access this workspace."),
    "invalid_session": (401, "Your session is invalid or expired. Sign in again."),
    "email_not_verified": (403, "Verify your email before accessing the workspace."),
    "workspace_access_denied": (403, "This account has not been authorized for this workspace."),
    "forbidden": (403, "Administrator access is required."),
    "auth_not_configured": (503, "Authentication is not configured on the server."),
    "auth_unavailable": (503, "The authentication service is temporarily unavailable."),
    "member_conflict": (409, "This member changed. Reload before editing."),
    "member_exists": (409, "This email is already authorized for the workspace."),
    "last_admin": (409, "Keep at least one active administrator."),
    "view_conflict": (409, "This saved view changed. Reload before editing."),
    "view_exists": (409, "You already have a saved view with this name."),
    "policy_conflict": (409, "This SLA policy changed. Reload before editing."),
    "sla_not_configured": (503, "The SLA policy is missing. Check database migrations."),
    "message_conflict": (409, "This message changed. Reload it before continuing."),
    "draft_exists": (409, "This ticket already has an open reply draft."),
    "invalid_message_state": (409, "This action is not available for the current message state."),
    "stale_reply": (409, "This ticket changed after approval. Review a new reply before sending."),
    "delivery_in_progress": (409, "Delivery is already in progress. Do not send it again."),
    "delivery_unknown": (409, "Delivery could not be confirmed. Check the mailbox before sending another reply."),
    "invalid_source_analysis": (422, "Select a supported analysis belonging to this ticket."),
    "mail_not_configured": (503, "Email delivery is not configured on the server."),
}


class DomainError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.status, self.message = ERRORS[code]
        super().__init__(code)


def error_response(code: str) -> JSONResponse:
    status, message = ERRORS[code]
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return error_response(error.code)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        # Never log exception strings: SQL/connection errors can include secrets or content.
        logger.error("database category=%s", type(error).__name__)
        if isinstance(error, DBAPIError) and (
            error.connection_invalidated or type(error).__name__ in {"OperationalError", "InterfaceError"}
        ):
            return error_response("database_unavailable")
        return error_response("internal_error")

    @app.middleware("http")
    async def safe_unexpected_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as error:
            # Catch before ServerErrorMiddleware re-raises into uvicorn's raw traceback log.
            logger.error("internal category=%s", type(error).__name__)
            return error_response("internal_error")
