import argparse
from pathlib import Path
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from app.config import load_settings
from app.db import create_database_engine
from app.errors import DomainError
from app.integrations.openrouter import OpenRouterClient
from app.models import Agent, KnowledgeDocument
from app.schemas import KnowledgeCreate
from app.services.knowledge import content_hash, ensure_embedding_model, ingest

AGENTS = (
    {"name": "Rayen Fassatoui", "email": "rayen@example.com"},
    {"name": "Demo Agent", "email": "agent@example.com"},
)


def seed(*, agents_only: bool = False) -> None:
    settings = load_settings()
    engine = create_database_engine(settings)
    sessions = sessionmaker(engine, expire_on_commit=False)
    try:
        with sessions.begin() as session:
            for agent in AGENTS:
                session.execute(insert(Agent).values(**agent).on_conflict_do_nothing(index_elements=[Agent.email]))
        print("Demo agents ready (idempotent by email).")
        if agents_only:
            return
        with httpx.Client(timeout=httpx.Timeout(45.0, connect=5.0, write=10.0, pool=5.0)) as http:
            provider = OpenRouterClient(http, settings)
            for path in sorted((Path(__file__).resolve().parents[1] / "knowledge").glob("*.md")):
                content = path.read_text(encoding="utf-8")
                title = content.splitlines()[0].removeprefix("# ").strip()
                with sessions() as session:
                    ensure_embedding_model(session, settings.openrouter_embedding_model)
                    existing = session.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.content_sha256 == content_hash(content)))
                if existing is not None:
                    print(f"Already indexed: {title}")
                    continue
                try:
                    ingest(sessions, provider, KnowledgeCreate(title=title, content=content, source_url=None))
                except DomainError as error:
                    if error.code != "duplicate_document":
                        raise
                    print(f"Already indexed: {title}")
                else:
                    print(f"Indexed: {title}")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo agents and immutable fictional AcmeCloud policies.")
    parser.add_argument("--agents-only", action="store_true", help="Seed only agents; no provider calls.")
    args = parser.parse_args()
    try:
        seed(agents_only=args.agents_only)
    except DomainError as error:
        print(f"Seed failed: {error.message}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError:
        print("Seed failed: check database configuration and connectivity.", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f"Seed failed ({type(error).__name__}). No secrets are logged; earlier documents remain usable.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
