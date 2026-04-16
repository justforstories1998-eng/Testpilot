"""
TestPilot Chat Schemas — v3.0
==============================
Request/response models for the chat API.
Key feature: ChatMessageResponse includes session_state so
the frontend can update its UI without a separate reload.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================
# Requests
# ============================================

class SendMessageRequest(BaseModel):
    """POST /api/v1/chat/send"""
    content: str = Field(..., min_length=1, max_length=10000)
    session_id: str


class AnalyzeUrlRequest(BaseModel):
    """POST /api/v1/chat/analyze-url"""
    url: str = Field(..., min_length=5)
    session_id: str


class AnalyzeUrlResponse(BaseModel):
    """Response from POST /api/v1/chat/analyze-url"""
    session_id: str
    url: str
    state: str
    is_login_page: bool
    confidence: float
    page_type: str
    page_title: str
    screenshot: Optional[str] = None


class GenerateTestsRequest(BaseModel):
    """POST /api/v1/chat/generate-tests"""
    url: str = Field(..., min_length=5)
    session_id: str
    additional_instructions: Optional[str] = None
    html_content: Optional[str] = None


class ExecuteTestsRequest(BaseModel):
    """POST /api/v1/chat/execute-tests"""
    session_id: str
    approved_destructive_ids: Optional[List[str]] = None
    skip_destructive: bool = True


class ApproveTestsRequest(BaseModel):
    """POST /api/v1/chat/approve-and-run"""
    session_id: str
    approved_test_ids: List[str]


# ============================================
# Responses — Messages
# ============================================

class ChatMessageResponse(BaseModel):
    """
    A single chat message returned by the API.
    Includes session_state so the frontend knows what
    buttons to show without a separate session reload.
    """
    id: str
    session_id: str
    role: str
    content: str
    message_type: str = "text"
    metadata: Optional[Dict[str, Any]] = None
    created_at: str
    session_state: Optional[str] = None

    @classmethod
    def from_mongo_doc(
        cls, doc: dict, session_state: str = None
    ) -> "ChatMessageResponse":
        return cls(
            id=str(doc["_id"]),
            session_id=doc.get("session_id", ""),
            role=doc.get("role", "assistant"),
            content=doc.get("content", ""),
            message_type=doc.get("message_type", "text"),
            metadata=doc.get("metadata"),
            created_at=_dt(doc.get("created_at")),
            session_state=session_state,
        )


# ============================================
# Responses — Sessions
# ============================================

class ChatSessionResponse(BaseModel):
    """Full chat session with messages and state."""
    id: str
    title: str
    target_url: Optional[str] = None
    is_active: bool = True
    state: str = "idle"
    login_required: bool = False
    login_completed: bool = False
    page_analysis: Optional[Dict[str, Any]] = None
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    last_report_path: Optional[str] = None
    created_at: str
    updated_at: str
    messages: List[ChatMessageResponse] = []

    @classmethod
    def from_mongo_doc(
        cls, doc: dict, messages: List[dict] = None
    ) -> "ChatSessionResponse":
        msg_list = [
            ChatMessageResponse.from_mongo_doc(m)
            for m in (messages or [])
        ]
        return cls(
            id=str(doc["_id"]),
            title=doc.get("title", "New Chat"),
            target_url=doc.get("target_url"),
            is_active=doc.get("is_active", True),
            state=doc.get("state", "idle"),
            login_required=doc.get("login_required", False),
            login_completed=doc.get("login_completed", False),
            page_analysis=doc.get("page_analysis"),
            total_tests=doc.get("total_tests", 0),
            passed_tests=doc.get("passed_tests", 0),
            failed_tests=doc.get("failed_tests", 0),
            last_report_path=doc.get("last_report_path"),
            created_at=_dt(doc.get("created_at")),
            updated_at=_dt(doc.get("updated_at")),
            messages=msg_list,
        )


class ChatSessionListItem(BaseModel):
    """Session summary for sidebar list."""
    id: str
    title: str
    target_url: Optional[str] = None
    state: str = "idle"
    message_count: int = 0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    created_at: str
    updated_at: str

    @classmethod
    def from_mongo_doc(
        cls, doc: dict, msg_count: int = 0
    ) -> "ChatSessionListItem":
        return cls(
            id=str(doc["_id"]),
            title=doc.get("title", "New Chat"),
            target_url=doc.get("target_url"),
            state=doc.get("state", "idle"),
            message_count=msg_count,
            total_tests=doc.get("total_tests", 0),
            passed_tests=doc.get("passed_tests", 0),
            failed_tests=doc.get("failed_tests", 0),
            created_at=_dt(doc.get("created_at")),
            updated_at=_dt(doc.get("updated_at")),
        )


# ============================================
# Responses — Generated Tests
# ============================================

class GeneratedTestResponse(BaseModel):
    """A generated test case with execution results."""
    id: str
    test_name: str
    test_category: str = "functional"
    priority: str = "medium"
    description: Optional[str] = None
    preconditions: List[str] = []
    tags: List[str] = []
    steps: List[Dict[str, Any]] = []
    expected_result: str = ""
    is_destructive: bool = False
    destructive_reason: Optional[str] = None
    status: str = "pending"
    actual_result: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    execution_time_ms: Optional[int] = None
    failure_analysis: Optional[Dict[str, Any]] = None
    created_at: str
    executed_at: Optional[str] = None

    @classmethod
    def from_mongo_doc(cls, doc: dict) -> "GeneratedTestResponse":
        return cls(
            id=str(doc["_id"]),
            test_name=doc.get("test_name", "Unnamed"),
            test_category=doc.get("test_category", "functional"),
            priority=doc.get("priority", "medium"),
            description=doc.get("description"),
            preconditions=doc.get("preconditions", []),
            tags=doc.get("tags", []),
            steps=doc.get("steps", []),
            expected_result=doc.get("expected_result", ""),
            is_destructive=doc.get("is_destructive", False),
            destructive_reason=doc.get("destructive_reason"),
            status=doc.get("status", "pending"),
            actual_result=doc.get("actual_result"),
            error_message=doc.get("error_message"),
            screenshot_path=doc.get("screenshot_path"),
            execution_time_ms=doc.get("execution_time_ms"),
            failure_analysis=doc.get("failure_analysis"),
            created_at=_dt(doc.get("created_at")),
            executed_at=_dt(doc.get("executed_at")),
        )


# ============================================
# Responses — Test Generation & Execution
# ============================================

class TestGenerationResponse(BaseModel):
    """Response from POST /api/v1/chat/generate-tests"""
    session_id: str
    page_analysis: Optional[Dict[str, Any]] = None
    test_cases: List[GeneratedTestResponse] = []
    total_tests: int = 0


class TestExecutionResponse(BaseModel):
    """Response from POST /api/v1/chat/execute-tests"""
    session_id: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    execution_time_ms: int = 0
    report_path: Optional[str] = None
    tests: List[GeneratedTestResponse] = []


# ============================================
# Utility
# ============================================

def _dt(dt) -> str:
    """Safely convert a datetime to ISO string."""
    if dt is None:
        return datetime.utcnow().isoformat()
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)