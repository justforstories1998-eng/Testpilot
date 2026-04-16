"""
TestPilot Dashboard API
========================
Provides stats for the frontend dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database import (
    chat_sessions_collection,
    generated_tests_collection,
    projects_collection,
)

logger = logging.getLogger("testpilot.api.dashboard")
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_iso(value: object) -> str | None:
    """
    Safely convert a datetime, string, or None to an ISO-8601 string.
    Returns None rather than raising for unexpected types.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # Make timezone-aware before serialising
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    # Already serialised (older documents stored as string)
    return str(value)


def _safe_float(value: object) -> float | None:
    """Return a float or None — never raises."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Route ──────────────────────────────────────────────────────────────────

@router.get("")
async def get_dashboard_stats() -> dict:
    """Return aggregate stats for the frontend dashboard."""
    try:
        projects_col = projects_collection()
        sessions_col = chat_sessions_collection()
        tests_col    = generated_tests_collection()

        # ── Counts ────────────────────────────────────────────────────
        total_projects = await projects_col.count_documents({})
        total_sessions = await sessions_col.count_documents({})
        total_tests    = await tests_col.count_documents({})
        passed_tests   = await tests_col.count_documents({"status": "passed"})
        failed_tests   = await tests_col.count_documents({"status": "failed"})

        executed = passed_tests + failed_tests
        overall_pass_rate = (
            round(passed_tests / executed * 100, 1) if executed > 0 else 0.0
        )

        # ── Recent projects ───────────────────────────────────────────
        recent_projects: list[dict] = []

        async for p in (
            projects_col.find({}).sort("updated_at", -1).limit(5)
        ):
            try:
                recent_projects.append({
                    "id":            str(p["_id"]),
                    "name":          str(p.get("name", "")),
                    "base_url":      str(p.get("base_url", "")),
                    "last_pass_rate": _safe_float(p.get("last_pass_rate")),
                    "updated_at":    _to_iso(p.get("updated_at")),
                })
            except Exception as doc_err:
                # Skip malformed documents rather than crashing the whole endpoint
                logger.warning(
                    f"Skipping malformed project doc {p.get('_id')}: {doc_err}"
                )

        return {
            "total_projects":    total_projects,
            "total_sessions":    total_sessions,
            "total_tests_run":   total_tests,
            "passed_tests":      passed_tests,
            "failed_tests":      failed_tests,
            "overall_pass_rate": overall_pass_rate,
            "recent_projects":   recent_projects,
        }

    except Exception as e:
        logger.exception(f"Dashboard aggregation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Dashboard aggregation failed: {str(e)}",
        )