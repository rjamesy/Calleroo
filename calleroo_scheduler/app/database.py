"""
Database models and session management for the Scheduler Service.
Uses SQLAlchemy with SQLite (async via aiosqlite).
"""

import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, String, Text, Integer, ForeignKey, create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

Base = declarative_base()


class ScheduledTask(Base):
    """Represents a scheduled call task."""

    __tablename__ = "scheduled_tasks"

    # Primary key
    id = Column(String(36), primary_key=True)

    # Status tracking
    status = Column(String(20), nullable=False, default="SCHEDULED")
    created_at = Column(String(30), nullable=False)
    updated_at = Column(String(30), nullable=False)

    # Schedule
    run_at_utc = Column(String(30), nullable=False)
    timezone = Column(String(50), nullable=True)

    # Task configuration
    agent_type = Column(String(50), nullable=False)
    conversation_id = Column(String(100), nullable=False)
    mode = Column(String(20), nullable=False)  # DIRECT or BRIEF_START

    # Call details
    place_id = Column(String(200), nullable=True)
    phone_e164 = Column(String(20), nullable=True)
    script_preview = Column(Text, nullable=True)

    # JSON payloads
    slots_json = Column(Text, nullable=True)
    place_json = Column(Text, nullable=True)  # For BRIEF_START mode
    disclosure_json = Column(Text, nullable=True)
    fallbacks_json = Column(Text, nullable=True)

    # Backend configuration
    backend_base_url = Column(String(200), nullable=False)
    backend_auth_token = Column(String(200), nullable=True)

    # Results
    call_id = Column(String(100), nullable=True)
    last_error = Column(Text, nullable=True)

    # Notification stub
    notify_target = Column(String(200), nullable=True)

    # Relationships
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")


class TaskEvent(Base):
    """Append-only log of task events."""

    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("scheduled_tasks.id"), nullable=False)
    ts_utc = Column(String(30), nullable=False)
    level = Column(String(10), nullable=False)  # INFO, WARN, ERROR
    message = Column(Text, nullable=False)

    # Relationships
    task = relationship("ScheduledTask", back_populates="events")


def get_database_url() -> str:
    """Get the database URL from environment or default."""
    db_path = os.environ.get("DATABASE_PATH", "./scheduler.db")
    return f"sqlite+aiosqlite:///{db_path}"


def get_sync_database_url() -> str:
    """Get synchronous database URL for migrations/setup."""
    db_path = os.environ.get("DATABASE_PATH", "./scheduler.db")
    return f"sqlite:///{db_path}"


# Async engine and session factory (initialized lazily)
_async_engine = None
_async_session_factory = None


async def get_async_engine():
    """Get or create the async engine."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            get_database_url(),
            echo=False,
        )
    return _async_engine


async def get_async_session_factory():
    """Get or create the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = await get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    factory = await get_async_session_factory()
    return factory()


async def init_database():
    """Initialize the database (create tables if not exist)."""
    engine = await get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database():
    """Close database connections."""
    global _async_engine, _async_session_factory
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None


def utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()
