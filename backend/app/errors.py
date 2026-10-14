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
