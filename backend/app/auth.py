from typing import Annotated
from urllib.parse import urlparse

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientConnectionError, PyJWKClientError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.errors import DomainError
from app.models import Member
from app.schemas import MemberRead
from app.services.members import member_read

bearer = HTTPBearer(auto_error=False)


class TokenVerifier:
    def __init__(self, settings: Settings):
        self.configured = bool(settings.neon_auth_base_url)
        base = urlparse(settings.neon_auth_base_url)
        self.origin = f"{base.scheme}://{base.netloc}"
        self.jwks = PyJWKClient(
            settings.neon_auth_jwks_url or settings.neon_auth_base_url + "/.well-known/jwks.json",
            cache_jwk_set=True, lifespan=300, timeout=5,
        ) if self.configured else None

    def verify(self, token: str) -> dict:
        if self.jwks is None:
            raise DomainError("auth_not_configured")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "EdDSA" or not isinstance(header.get("kid"), str) or len(header["kid"]) > 200:
                raise DomainError("invalid_session")
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, signing_key.key, algorithms=["EdDSA"], issuer=self.origin, audience=self.origin,
                options={"require": ["exp", "iat", "sub", "email", "emailVerified"]},
            )
        except PyJWKClientConnectionError:
            raise DomainError("auth_unavailable") from None
        except (InvalidTokenError, PyJWKClientError, ValueError, TypeError, KeyError):
            raise DomainError("invalid_session") from None
        if not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 200:
            raise DomainError("invalid_session")
        if not isinstance(claims["email"], str) or len(claims["email"]) > 320 or claims.get("banned") is True:
            raise DomainError("invalid_session")
        if claims["emailVerified"] is not True:
            raise DomainError("email_not_verified")
        return claims


def current_member(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> MemberRead:
    if credentials is None:
        raise DomainError("authentication_required")
    token = credentials.credentials
    if not token or len(token) > 16384:
        raise DomainError("invalid_session")
    claims = request.app.state.token_verifier.verify(token)
    email = claims["email"].strip().lower()
    try:
        with request.app.state.sessions.begin() as session:
            member = session.scalar(select(Member).where(Member.email == email).with_for_update())
            if member is None or not member.active:
                raise DomainError("workspace_access_denied")
            if member.auth_subject is None:
                member.auth_subject = claims["sub"]
                session.flush()
            elif member.auth_subject != claims["sub"]:
                raise DomainError("workspace_access_denied")
            return member_read(member)
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "members_auth_subject_key":
            raise DomainError("workspace_access_denied") from None
        raise


def require_admin(member: Annotated[MemberRead, Depends(current_member)]) -> MemberRead:
    if member.role != "admin":
        raise DomainError("forbidden")
    return member
