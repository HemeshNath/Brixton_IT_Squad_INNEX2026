"""Database engine, session and tables (SQLAlchemy 2.0).

SQLite during development, Supabase Postgres in production (DATABASE_URL).
User ids are Firebase UIDs stored as text. Message text is always stored masked.
Tables are created by Alembic migrations (backend/migrations), not by the app."""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import (JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, create_engine,
                        event)
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
    is_admin: Mapped[bool] = mapped_column(default=False)  # old Phase 10 flag, unused since the admin panel (10A)
    blocked: Mapped[bool] = mapped_column(default=False)  # blocked users get 403 from every app endpoint (10A)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # last app request
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
    source: Mapped[str] = mapped_column(String(8), default="none")  # whoisxml | rdap | whois | none
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # full WHOIS details (backend flow B3)


class AdminUser(Base):
    """Web admin panel account (Phase 10A): ID + password, separate from the app's Google users."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # stored lower case
    password_hash: Mapped[str] = mapped_column(String(255))  # scrypt, never the password itself
    role: Mapped[str] = mapped_column(String(16), default="reviewer")  # owner | admin | reviewer
    active: Mapped[bool] = mapped_column(default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminSession(Base):
    """A signed-in admin browser. Only a hash of the cookie value is stored."""

    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie value
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Every admin action: who, what, when (Phase 10A)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_username: Mapped[str] = mapped_column(String(64), default="", index=True)
    action: Mapped[str] = mapped_column(String(64))  # e.g. login, login_failed, report_approved
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SettingsVersion(Base):
    """One saved version of the live system settings (Phase 10A step A4). The newest number is in use."""

    __tablename__ = "settings_versions"

    number: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # 1, 2, 3...
    data: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    restored_from: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set when made by "undo"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    """An API key set in the admin panel (Phase 10A step A5), stored encrypted. Wins over the .env value."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)  # otx | whois
    encrypted: Mapped[str] = mapped_column(Text)  # Fernet token, never the key itself
    last4: Mapped[str] = mapped_column(String(8), default="")
    tested_ok: Mapped[bool] = mapped_column(default=False)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Ad(Base):
    """A home-screen banner ad in the phone app (Phase 10A step A9). It can only be switched on when its link passed
    the safety check (OTX, WHOIS domain age, block list); it shows between starts_at and ends_at."""

    __tablename__ = "ads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(String(200), default="")
    link: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8), default="all")  # en | ne | all
    image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # PNG / JPEG, at most 500 KB
    image_type: Mapped[str] = mapped_column(String(32), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=False)
    link_check: Mapped[dict] = mapped_column(JSON, default=dict)  # {"ok", "problems", "notes", "checked_at"}
    views: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AppConfig(Base):
    """App control (Phase 10A step A10): one row per key, e.g. "app" = minimum version, notice, chat-apps switch."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ModelTest(Base):
    """One test run of an AI model version on the data set (Phase 10A step A5)."""

    __tablename__ = "model_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    started_by: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelChoice(Base):
    """Which approved AI model version is in use; the newest row wins (Phase 10A step A5)."""

    __tablename__ = "model_choices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(String(64))
    chosen_by: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ListEntry(Base):
    """An admin panel change to a list (Phase 10A step A6): an added entry, or (active=False) a switched-off
    built-in entry from trusted.json. Lists: trusted_domain, trusted_sender, blocked_domain, blocked_sender."""

    __tablename__ = "list_entries"
    __table_args__ = (UniqueConstraint("list", "value", name="uq_list_entries_list_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(String(255))  # normalised domain / sender
    label: Mapped[str] = mapped_column(String(200), default="")  # company (trusted lists) or reason (blocked lists)
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
