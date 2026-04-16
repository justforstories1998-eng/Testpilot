"""
TestPilot Database — Async MongoDB via Motor
=============================================
Collections:
    - projects
    - chat_sessions
    - chat_messages
    - generated_tests
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

logger = logging.getLogger("testpilot.database")

# ── Module-level singletons ────────────────────────────────────────────────
_client:   Optional[AsyncIOMotorClient]   = None
_database: Optional[AsyncIOMotorDatabase] = None


# ── Client / database accessors ────────────────────────────────────────────

def get_client() -> AsyncIOMotorClient:
    """
    Return the Motor client, creating it on first call.
    Safe to call before connect_to_mongodb() — the ping happens there.
    """
    global _client
    if _client is None:
        # Import here to avoid a circular import at module load time
        from app.config import get_settings
        settings = get_settings()

        if not settings.MONGODB_URI:
            raise RuntimeError(
                "MONGODB_URI is not set. "
                "Add it to your .env file before starting the server."
            )

        _client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            maxPoolSize=20,
            minPoolSize=2,
            serverSelectionTimeoutMS=10_000,
            retryWrites=True,
            appName="TestPilot",
        )
        logger.debug("Motor client created")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    """Return the Motor database handle, initialising it if necessary."""
    global _database
    if _database is None:
        from app.config import get_settings
        _database = get_client()[get_settings().MONGODB_DB_NAME]
        logger.debug(f"Database handle acquired: {_database.name}")
    return _database


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Return an arbitrary collection by name."""
    return get_database()[name]


# ── Typed collection accessors ─────────────────────────────────────────────
# Each is a plain function (not async) that returns the Motor collection.
# Motor collections are not coroutines — await the *operations* on them.

def projects_collection() -> AsyncIOMotorCollection:
    return get_collection("projects")


def chat_sessions_collection() -> AsyncIOMotorCollection:
    return get_collection("chat_sessions")


def chat_messages_collection() -> AsyncIOMotorCollection:
    return get_collection("chat_messages")


def generated_tests_collection() -> AsyncIOMotorCollection:
    return get_collection("generated_tests")


# ── Lifecycle ──────────────────────────────────────────────────────────────

async def connect_to_mongodb() -> bool:
    """
    Verify the connection with a ping, then create indexes.
    Call this once during application startup (lifespan handler).
    """
    try:
        client = get_client()
        await client.admin.command("ping")
        db = get_database()
        logger.info(f"MongoDB connected — database: {db.name}")
        await create_indexes()
        return True
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise


async def close_mongodb_connection() -> None:
    """
    Close the Motor client and reset the module-level singletons.
    Call this during application shutdown (lifespan handler).
    """
    global _client, _database
    if _client is not None:
        _client.close()
        _client   = None
        _database = None
        logger.info("MongoDB connection closed")


# ── Index management ───────────────────────────────────────────────────────

async def create_indexes() -> None:
    """
    Ensure indexes exist for all hot query paths.
    Uses background=True so existing data is not locked during creation.
    Safe to call on every startup — MongoDB is idempotent for existing indexes.
    """
    try:
        # projects
        p = projects_collection()
        await p.create_index("name",       background=True)
        await p.create_index("created_at", background=True)
        await p.create_index("updated_at", background=True)

        # chat_sessions
        s = chat_sessions_collection()
        await s.create_index(
            [("project_id", 1), ("is_active", 1)],
            background=True,
        )
        await s.create_index(
            [("project_id", 1), ("updated_at", -1)],
            background=True,
        )
        await s.create_index("updated_at", background=True)

        # chat_messages  — most frequently queried collection
        m = chat_messages_collection()
        await m.create_index(
            [("session_id", 1), ("created_at", 1)],
            background=True,
        )

        # generated_tests
        g = generated_tests_collection()
        await g.create_index("session_id", background=True)
        await g.create_index(
            [("session_id", 1), ("created_at", 1)],
            background=True,
        )

        logger.info("Database indexes verified / created")

    except Exception as e:
        # Non-fatal: log and continue — queries still work without indexes
        logger.warning(f"Index creation warning (non-fatal): {e}")


# ── Health check ───────────────────────────────────────────────────────────

async def check_mongodb_health() -> dict:
    """
    Ping MongoDB and return latency + collection list.
    Used by the /api/v1/health endpoint.
    """
    try:
        client = get_client()
        t0     = time.monotonic()
        await client.admin.command("ping")
        latency_ms = round((time.monotonic() - t0) * 1000, 2)

        db          = get_database()
        collections = await db.list_collection_names()

        return {
            "connected":    True,
            "latency_ms":   latency_ms,
            "database":     db.name,
            "collections":  collections,
        }

    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return {
            "connected": False,
            "error":     str(e),
        }