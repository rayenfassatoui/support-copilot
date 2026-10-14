from concurrent.futures import ThreadPoolExecutor
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import jwt
import pytest
from sqlalchemy import select

from app.auth import TokenVerifier, current_member
from app.models import Member
from app.services.members import bootstrap_admin


@pytest.fixture
def signed_session(client, application, settings, member, monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(private.public_key()))
    public.update(kid="workspace-test-key", use="sig", alg="EdDSA")
    verifier = TokenVerifier(settings.model_copy(update={"neon_auth_base_url": "https://auth.example.com/workspace/auth", "neon_auth_jwks_url": "https://auth.example.com/workspace/auth/.well-known/jwks.json"}))
    monkeypatch.setattr(verifier.jwks, "fetch_data", lambda: {"keys": [public]})
    application.state.token_verifier = verifier
    application.dependency_overrides.pop(current_member)

    def issue(**overrides):
        now = int(time.time())
        claims = {"sub": "verified-owner", "email": str(member.email), "emailVerified": True, "iss": verifier.origin, "aud": verifier.origin, "iat": now, "exp": now + 900}
        claims.update(overrides)
        return {"Authorization": "Bearer " + jwt.encode(claims, private, algorithm="EdDSA", headers={"kid": public["kid"]})}
    return issue


@pytest.mark.parametrize("path", ["/tickets", "/agents", "/knowledge", "/members", "/views", "/sla-policies", "/delivery/config"])
def test_anonymous_access_is_denied(client, application, path):
    application.dependency_overrides.pop(current_member)
    response = client.get("/api" + path)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_verified_account_is_bound_once_and_roles_are_database_owned(client, signed_session, sessions, member):
    headers = signed_session(role="agent")
    identity = client.get("/api/auth/me", headers=headers)
    assert identity.status_code == 200
    assert identity.json()["registered"] is True
    assert identity.json()["role"] == "admin"
    with sessions.begin() as session:
        stored = session.get(Member, member.id)
        assert stored.auth_subject == "verified-owner"
        stored.role = "agent"
    assert client.get("/api/tickets", headers=headers).status_code == 200
    assert client.get("/api/members", headers=signed_session(role="admin")).status_code == 403
    assert client.post("/api/knowledge", headers=headers, json={"title": "Protected policy", "content": "Only an admin may add a policy to the knowledge base."}).status_code == 403
    assert client.patch("/api/sla-policies/high", headers=headers, json={"version": 1, "first_response_minutes": 10, "resolution_minutes": 60}).status_code == 403
    with sessions.begin() as session:
        session.get(Member, member.id).active = False
    assert client.get("/api/tickets", headers=headers).status_code == 403


@pytest.mark.parametrize("claims,status", [
    ({"emailVerified": False}, 403), ({"emailVerified": "true"}, 403),
    ({"email": "uninvited@example.com"}, 403), ({"exp": 1}, 401),
    ({"iss": "https://another.example.com"}, 401), ({"aud": "another-api"}, 401),
    ({"banned": True}, 401), ({"sub": ""}, 401), ({"email": []}, 401),
])
def test_invalid_or_unauthorized_identity_never_binds_member(client, signed_session, sessions, member, claims, status):
    response = client.get("/api/auth/me", headers=signed_session(**claims))
    assert response.status_code == status
    with sessions() as session:
        assert session.get(Member, member.id).auth_subject is None


def test_subject_change_and_signature_forgery_are_rejected(client, signed_session):
    headers = signed_session()
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=signed_session(sub="replacement-identity")).status_code == 403
    token = headers["Authorization"].split()[1]
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode(claims, Ed25519PrivateKey.generate(), algorithm="EdDSA", headers={"kid": "workspace-test-key"})
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + forged}).status_code == 401


def test_jwks_outage_is_not_misreported_as_invalid_credentials(client, signed_session, application, monkeypatch):
    from jwt.exceptions import PyJWKClientConnectionError
    def unavailable():
        raise PyJWKClientConnectionError("provider unavailable")
    monkeypatch.setattr(application.state.token_verifier.jwks, "fetch_data", unavailable)
    response = client.get("/api/auth/me", headers=signed_session())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_unavailable"


def test_authorized_email_reuses_agent_and_conflicts_preserve_access(client, agents, member):
    response = client.post("/api/members", json={"name": "New operator", "email": agents[1]["email"].upper(), "role": "agent"})
    assert response.status_code == 201
    account = response.json()
    assert account["agent_id"] == agents[1]["id"]
    assert account["registered"] is False
    duplicate = client.post("/api/members", json={"name": "Duplicate", "email": agents[1]["email"], "role": "admin"})
    assert duplicate.status_code == 409
    last = client.patch(f"/api/members/{member.id}", json={"version": 1, "role": "agent", "active": True})
    assert last.status_code == 409
    assert last.json()["detail"]["code"] == "last_admin"
    updated = client.patch(f"/api/members/{account['id']}", json={"version": 1, "role": "admin", "active": True})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    stale = client.patch(f"/api/members/{account['id']}", json={"version": 1, "role": "agent", "active": False})
    assert stale.status_code == 409
    assert next(row for row in client.get("/api/members").json() if row["id"] == account["id"])["active"] is True


def test_simultaneous_admin_demotions_preserve_one_active_admin(client, member, sessions):
    second = client.post("/api/members", json={"name": "Second admin", "email": "second@example.com", "role": "admin"}).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda account_id: client.patch(f"/api/members/{account_id}", json={"version": 1, "role": "agent", "active": True}), [str(member.id), second["id"]]))
    assert sorted(response.status_code for response in attempts) == [200, 409]
    with sessions() as session:
        admins = session.scalars(select(Member).where(Member.active.is_(True), Member.role == "admin")).all()
        assert len(admins) == 1


def test_bootstrap_does_not_reactivate_or_replace_existing_members(sessions, settings):
    configured = settings.model_copy(update={"bootstrap_admin_email": "owner@example.com"})
    bootstrap_admin(sessions, configured)
    with sessions.begin() as session:
        owner = session.scalar(select(Member))
        assert owner.email == "owner@example.com" and owner.role == "admin"
        owner.active = False
    bootstrap_admin(sessions, configured.model_copy(update={"bootstrap_admin_email": "other@example.com"}))
    with sessions() as session:
        rows = session.scalars(select(Member)).all()
        assert len(rows) == 1
        assert rows[0].email == "owner@example.com" and rows[0].active is False
