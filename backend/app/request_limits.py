from fastapi import HTTPException
from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 11 * 1024 * 1024
DETAIL = {"code": "request_too_large", "message": "Request exceeds the 11 MB upload envelope. Files may be at most 10 MB."}


class RequestBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length" and (not value.isdigit() or int(value) > MAX_REQUEST_BYTES):
                await JSONResponse({"detail": DETAIL}, status_code=413)(scope, receive, send)
                return
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > MAX_REQUEST_BYTES:
                raise HTTPException(413, detail=DETAIL)
            return message

        await self.app(scope, bounded_receive, send)
