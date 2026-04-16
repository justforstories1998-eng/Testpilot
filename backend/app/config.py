"""
TestPilot Configuration
========================
Clean settings with only what's actually used.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── MongoDB ────────────────────────────────────────────────────────
    MONGODB_URI:     str = ""
    MONGODB_DB_NAME: str = "testpilot"

    # ── Storage ────────────────────────────────────────────────────────
    STORAGE_PATH: str = "../storage"

    # ── Security ───────────────────────────────────────────────────────
    SECRET_KEY: str = "change-this-to-a-random-secret-key"

    # ── Groq AI ────────────────────────────────────────────────────────
    GROQ_API_KEY:      str   = ""
    GROQ_MODEL:        str   = "llama-3.3-70b-versatile"
    GROQ_MAX_TOKENS:   int   = 8192
    GROQ_TEMPERATURE:  float = 0.1

    # ── Playwright ─────────────────────────────────────────────────────
    # PAGE_LOAD_TIMEOUT is in milliseconds (Playwright convention)
    PAGE_LOAD_TIMEOUT:    int = 30_000   # 30 s
    # Launch browser in headless mode when configured or when GUI is unavailable
    PLAYWRIGHT_HEADLESS: bool = False
    # How long a browser session may sit idle before being reaped
    BROWSER_IDLE_TIMEOUT: int = 900      # 15 min in seconds

    # ── Server ─────────────────────────────────────────────────────────
    BASE_URL: str = "http://localhost:8000"

    # ── Safety ─────────────────────────────────────────────────────────
    DANGEROUS_KEYWORDS: List[str] = [
        "delete", "remove", "reset", "clear", "destroy",
        "drop", "erase", "terminate", "purge", "deactivate",
    ]

    # ── Computed paths ─────────────────────────────────────────────────

    @property
    def screenshots_dir(self) -> Path:
        return self._resolve("screenshots")

    @property
    def reports_dir(self) -> Path:
        return self._resolve("reports")

    @property
    def storage_base(self) -> Path:
        return self._resolve("")

    # ── Feature flags ──────────────────────────────────────────────────

    @property
    def groq_configured(self) -> bool:
        return bool(
            self.GROQ_API_KEY
            and not self.GROQ_API_KEY.startswith("gsk_your")
        )

    # ── Internal helpers ───────────────────────────────────────────────

    def _resolve(self, sub: str) -> Path:
        """
        Resolve a storage sub-directory relative to the backend root,
        creating it if it does not already exist.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        base = Path(self.STORAGE_PATH)
        if not base.is_absolute():
            base = backend_dir / base
        full = (base / sub) if sub else base
        full.mkdir(parents=True, exist_ok=True)
        return full

    # ── Validators ─────────────────────────────────────────────────────

    @field_validator("MONGODB_URI")
    @classmethod
    def validate_mongo(cls, v: str) -> str:
        v = v.strip()
        if not v:
            # Allow empty string so the app can start without Mongo
            # configured; connection errors surface at query time.
            return v
        if not (
            v.startswith("mongodb://")
            or v.startswith("mongodb+srv://")
        ):
            raise ValueError(
                "MONGODB_URI must start with mongodb:// or mongodb+srv://"
            )
        return v

    # ── Pydantic config ────────────────────────────────────────────────

    class Config:
        env_file          = ".env"
        env_file_encoding = "utf-8"
        extra             = "ignore"


# ── Singleton ──────────────────────────────────────────────────────────────

@lru_cache()
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Looks for a .env file in the backend root directory first;
    falls back to environment variables only if no file is found.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    env_file    = backend_dir / ".env"
    if env_file.exists():
        return Settings(_env_file=str(env_file))
    return Settings()