"""
TestPilot FastAPI Application
==============================
AI-powered automated web testing platform.
Chat-driven Selenium testing with Groq AI.
"""

import logging
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import connect_to_mongodb, close_mongodb_connection

logger = logging.getLogger("testpilot")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    settings = get_settings()

    # ── MongoDB ────────────────────────────────────────────────────────
    try:
        await connect_to_mongodb()
        logger.info("MongoDB connected")
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}")

    # ── Storage directories ────────────────────────────────────────────
    for d in (settings.screenshots_dir, settings.reports_dir):
        Path(d).mkdir(parents=True, exist_ok=True)

    # ── Install Playwright browsers on first run ───────────────────────
    try:
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("Playwright Chromium installed/verified")
        else:
            logger.warning(
                f"Playwright install returned code {result.returncode}: "
                f"{result.stderr.decode(errors='replace').strip()}"
            )
    except FileNotFoundError:
        # playwright CLI not on PATH — try the module entrypoint
        try:
            result = subprocess.run(
                ["python", "-m", "playwright", "install", "chromium"],
                capture_output=True,
                timeout=120,
            )
            logger.info("Playwright Chromium installed via python -m playwright")
        except Exception as e:
            logger.warning(f"Playwright install fallback failed: {e}")
    except Exception as e:
        logger.warning(f"Playwright install check failed: {e}")

    # ── Browser session cleanup loop ───────────────────────────────────
    try:
        from app.services.playwright_manager import playwright_manager
        await playwright_manager.start_cleanup_loop()
        logger.info("Playwright cleanup loop started")
    except Exception as e:
        logger.warning(f"Browser cleanup loop failed: {e}")

    # ── Groq AI status ─────────────────────────────────────────────────
    if settings.groq_configured:
        logger.info(f"Groq AI ready (model: {settings.GROQ_MODEL})")
    else:
        logger.warning(
            "Groq AI NOT configured. Set GROQ_API_KEY in .env"
        )

    yield  # ── Application running ─────────────────────────────────────

    # ── Shutdown: stop cleanup loop ────────────────────────────────────
    try:
        from app.services.playwright_manager import playwright_manager
        await playwright_manager.stop_cleanup_loop()
        logger.info("Playwright cleanup loop stopped")
    except Exception:
        pass

    # ── Shutdown: close MongoDB ────────────────────────────────────────
    try:
        await close_mongodb_connection()
        logger.info("MongoDB disconnected")
    except Exception:
        pass


# ── Application instance ───────────────────────────────────────────────────
app = FastAPI(
    title="TestPilot",
    description="AI-powered automated web testing platform",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ───────────────────────────────────────────────────────────
settings = get_settings()
for _name in ("screenshots", "reports"):
    _path = Path(getattr(settings, f"{_name}_dir"))
    _path.mkdir(parents=True, exist_ok=True)
    app.mount(
        f"/static/{_name}",
        StaticFiles(directory=str(_path)),
        name=_name,
    )

# ── API Routes ─────────────────────────────────────────────────────────────
from app.api.routes import health, projects, dashboard
from app.api.routes import chat as chat_routes

app.include_router(
    health.router,
    prefix="/api/v1",
    tags=["Health"],
)
app.include_router(
    projects.router,
    prefix="/api/v1/projects",
    tags=["Projects"],
)
app.include_router(
    dashboard.router,
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)
app.include_router(
    chat_routes.router,
    prefix="/api/v1/chat",
    tags=["AI Chat"],
)
app.include_router(chat_routes.ws_router)


@app.get("/", tags=["Root"])
async def root():
    s = get_settings()
    return {
        "service": "TestPilot",
        "version": "2.0.0",
        "docs": "/docs",
        "groq_configured": s.groq_configured,
    }