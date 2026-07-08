"""SQLAlchemy engine + session.

Two backends, picked by `DATABASE_URL` (see app/config.py):
  • postgres — Supabase pooler. NullPool + no prepared statements (pgbouncer-safe).
  • sqlite   — local dev. `check_same_thread=False` so FastAPI's threadpool can
    share the connection; StaticPool for `:memory:` (one shared in-mem DB).
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings

settings = get_settings()

if settings.is_sqlite:
    _is_memory = ":memory:" in settings.database_url or settings.database_url in (
        "sqlite://",
        "sqlite:///:memory:",
    )
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool if _is_memory else None,
        future=True,
    )
else:
    engine = create_engine(
        settings.database_url,
        # pgbouncer (transaction pooler) can't keep prepared statements; NullPool
        # avoids cross-request connection reuse in serverless.
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
