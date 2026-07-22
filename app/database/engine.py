"""SQLAlchemy engine/session bootstrap.

This module owns exactly the mechanics of connecting to the database: the
`Engine`, the declarative `Base` that ORM models (added in Phase 2) will
subclass, and a session factory. Nothing here knows about trades,
positions, or reports — the ORM models and repositories added in later
phases build on top of this.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import Settings, get_settings


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the app."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Provide a transactional session: commits on success, rolls back on error."""
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(settings: Settings | None = None) -> None:
    """Create all tables registered on `Base`. Safe to call repeatedly."""
    Base.metadata.create_all(bind=get_engine(settings))
