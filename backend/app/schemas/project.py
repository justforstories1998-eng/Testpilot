"""
TestPilot Project Schemas — Simplified
========================================
"""

from __future__ import annotations
import math
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    base_url: str
    tags: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name is required")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("Base URL is required")
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, v):
        if isinstance(v, list):
            return [t.strip().lower() for t in v if isinstance(t, str) and t.strip()]
        return v


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    tags: Optional[List[str]] = None

    def to_update_dict(self) -> dict:
        from datetime import timezone
        data = {}
        for field_name, value in self.model_dump().items():
            if value is not None:
                data[field_name] = value
        data["updated_at"] = datetime.now(timezone.utc)
        return data


class ProjectSummaryResponse(BaseModel):
    id: str
    name: str
    base_url: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    total_sessions: int = 0
    last_test_at: Optional[datetime] = None
    last_pass_rate: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "ProjectSummaryResponse":
        return cls(
            id=str(doc["_id"]),
            name=doc.get("name", ""),
            base_url=doc.get("base_url", ""),
            description=doc.get("description", ""),
            tags=doc.get("tags", []),
            total_sessions=doc.get("total_sessions", 0),
            last_test_at=doc.get("last_test_at"),
            last_pass_rate=doc.get("last_pass_rate"),
            created_at=doc.get("created_at", datetime.utcnow()),
            updated_at=doc.get("updated_at", datetime.utcnow()),
        )


class ProjectDetailResponse(ProjectSummaryResponse):
    """Same as summary — projects are simple now."""
    pass


class ProjectListResponse(BaseModel):
    items: List[ProjectSummaryResponse] = []
    total: int = 0
    page: int = 1
    limit: int = 20
    total_pages: int = 0

    @classmethod
    def create(cls, items, total, page, limit):
        return cls(
            items=items, total=total, page=page, limit=limit,
            total_pages=math.ceil(total / limit) if limit > 0 else 0,
        )


class ProjectCreatedResponse(BaseModel):
    id: str
    name: str
    base_url: str
    message: str = "Project created successfully"


class ProjectDeletedResponse(BaseModel):
    id: str
    message: str = "Project deleted successfully"