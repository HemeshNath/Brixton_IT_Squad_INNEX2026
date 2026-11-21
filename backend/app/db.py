"""Database engine, session and tables (SQLAlchemy 2.0).

SQLite during development, Supabase Postgres in production (DATABASE_URL).
User ids are Firebase UIDs stored as text. Message text is always stored masked.
Tables are created by Alembic migrations (backend/migrations), not by the app."""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    uid: Mapped[str] = mapped_column(String(128), primary_key=True)  # Firebase UID
    email: Mapped[str] = mapped_column(String(320), default="")
    plan: Mapped[str] = mapped_column(String(16), default="free")  # free | premium
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    checks: Mapped[list[Check]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Check(Base):
    __tablename__ = "checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.uid", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # sms | notification | link | manual
    source_app: Mapped[str] = mapped_column(String(128), default="")
    sender: Mapped[str] = mapped_column(String(128), default="")
    text: Mapped[str] = mapped_column(Text, default="")  # masked only
    verdict: Mapped[str] = mapped_column(String(16))  # safe | suspicious | dangerous
    score: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    not_sure: Mapped[bool] = mapped_column(default=False)
    probabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    links: Mapped[list] = mapped_column(JSON, default=list)
    suggestion: Mapped[str] = mapped_column(Text, default="")
    checks_skipped: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    option_set_version: Mapped[str] = mapped_column(String(32), default="")
    timings_ms: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[Profile] = relationship(back_populates="checks")


class Feedback(Base):
    """'Wrong result?' / scam reports. Reviewed by an admin before use as data."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.uid", ondelete="CASCADE"), index=True)
    check_id: Mapped[str | None] = mapped_column(ForeignKey("checks.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")  # masked
    correct_label: Mapped[str] = mapped_column(String(8))  # ham | spam | scam
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnownScam(Base):
    """Approved scam messages for the known-scam memory (Phase 8)."""

    __tablename__ = "known_scams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text)  # masked
    category: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(32), default="collected")  # collected | feedback
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # float32 vector
    embedding_model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OtxCache(Base):
    """AlienVault OTX answer per IP or domain, reused for otx_cache_hours (Phase 4).
    One row per OTX call, so counting today's rows also counts today's OTX calls (daily limit)."""

    __tablename__ = "otx_cache"

    indicator: Mapped[str] = mapped_column(String(270), primary_key=True)  # "ip:1.2.3.4" or "domain:example.com"
    kind: Mapped[str] = mapped_column(String(8))  # ip | domain
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    pulse_count: Mapped[int] = mapped_column(Integer, default=0)
    whitelisted: Mapped[bool] = mapped_column(default=False)  # OTX marks well-known safe indicators
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DomainCache(Base):
    """Domain registration data from RDAP/WHOIS, reused for domain_cache_days (Phase 5).
    source "none" = no public data (e.g. most .np domains) -> age unknown, never counted as risky."""

    __tablename__ = "domain_cache"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registrar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="none")  # rdap | whois | none
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        engine = create_engine(database_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_fk_on(dbapi_conn, _):  # SQLite ignores foreign keys unless asked
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # Supabase (pooler) closes idle connections: test each connection before use (pre_ping) and replace
    # connections older than 5 minutes (recycle), so a dropped connection never fails a check.
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with request.app.state.sessionmaker() as session:
        yield session
