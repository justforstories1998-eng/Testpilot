"""
TestPilot Project Model — Simplified
======================================
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class ProjectDocument(BaseModel):
    """Project document stored in MongoDB."""
    name: str
    description: Optional[str] = ""
    base_url: str
    tags: List[str] = Field(default_factory=list)

    # Stats
    total_sessions: int = 0
    last_test_at: Optional[datetime] = None
    last_pass_rate: Optional[float] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name cannot be empty")
        return v

    def to_mongo(self) -> dict:
        data = self.model_dump()
        data["updated_at"] = datetime.now(timezone.utc)
        return data