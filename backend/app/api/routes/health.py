"""
TestPilot Health Check — Simplified
=====================================
"""

from fastapi import APIRouter
from app.database import check_mongodb_health
from app.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "TestPilot", "version": "2.0.0"}


@router.get("/health/detailed")
async def detailed_health():
    settings = get_settings()
    mongo = await check_mongodb_health()

    chrome_ok = False
    try:
        import shutil
        chrome_ok = bool(
            shutil.which("google-chrome") or
            shutil.which("chrome") or
            shutil.which("chromium")
        )
    except Exception:
        pass

    overall = "healthy" if mongo.get("connected") else "unhealthy"

    return {
        "status": overall,
        "components": {
            "mongodb": mongo,
            "groq_ai": {
                "configured": settings.groq_configured,
                "model": settings.GROQ_MODEL if settings.groq_configured else None,
            },
            "chrome": {"available": chrome_ok},
        },
    }