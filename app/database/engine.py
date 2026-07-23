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


_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker[Session]] = {}


def get_engine(settings: Settings | None = None) -> Engine:
    """Return the (process-wide) engine for `settings.database_url`.

    Keyed by database URL rather than a single unconditional singleton:
    the real app only ever uses one `Settings`/one database per process,
    so this is still effectively a singleton in production, but it also
    means two different `Settings` instances (as happens across tests,
    or the scheduler/dashboard pointed at different databases) each get
    their own engine instead of silently sharing whichever one was
    created first.
    """
    settings = settings or get_settings()
    url = settings.database_url
    if url not in _engines:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        _engines[url] = create_engine(url, connect_args={"check_same_thread": False})
    return _engines[url]


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or get_settings()
    url = settings.database_url
    if url not in _session_factories:
        _session_factories[url] = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
    return _session_factories[url]


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
