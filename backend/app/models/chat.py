"""
TestPilot Chat Models — With Session State Machine
====================================================
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger("testpilot.models.chat")


# ============================================
# Enums
# ============================================

class SessionState(str, Enum):
    """State machine for chat-driven testing flow."""
    IDLE = "idle"                       # Just created, no URL analyzed
    ANALYZING = "analyzing"             # Currently analyzing a URL
    WAITING_LOGIN = "waiting_login"     # Login detected, waiting for user
    LOGIN_DONE = "login_done"           # User finished login
    READY_TO_GENERATE = "ready"         # Page analyzed, ready to generate tests
    GENERATING = "generating"           # Generating test code
    TESTS_READY = "tests_ready"         # Tests generated, ready to run
    EXECUTING = "executing"             # Tests running
    AWAITING_APPROVAL = "awaiting_approval"  # Destructive tests need approval
    COMPLETED = "completed"             # All done, report available


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, Enum):
    TEXT = "text"
    CODE = "code"
    TEST_RESULT = "test_result"
    REPORT = "report"
    ERROR = "error"
    STATUS = "status"


class GeneratedTestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


# ============================================
# Chat Session Document
# ============================================

class ChatSessionDocument(BaseModel):
    """MongoDB document for a chat session with state tracking."""
    project_id: str = ""
    title: str = "New Chat"
    target_url: Optional[str] = None
    is_active: bool = True

    # State machine
    state: SessionState = SessionState.IDLE

    # Analysis data
    page_analysis: Optional[Dict[str, Any]] = None
    login_required: bool = False
    login_completed: bool = False
    browser_session_active: bool = False

    # Test data
    test_generation_data: Optional[Dict[str, Any]] = None
    last_report_path: Optional[str] = None

    # Stats
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0

    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["state"] = self.state.value
        for k in ("created_at", "updated_at"):
            if isinstance(doc.get(k), datetime):
                doc[k] = doc[k].replace(tzinfo=None)
        return doc


# ============================================
# Chat Message Document
# ============================================

class ChatMessageDocument(BaseModel):
    """MongoDB document for a single chat message."""
    session_id: str
    role: MessageRole = MessageRole.ASSISTANT
    content: str = ""
    message_type: MessageType = MessageType.TEXT
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["role"] = self.role.value
        doc["message_type"] = self.message_type.value
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].replace(tzinfo=None)
        return doc


# ============================================
# Generated Test Document
# ============================================

class GeneratedTestDocument(BaseModel):
    """MongoDB document for an AI-generated test case."""
    session_id: str
    project_id: str = ""
    test_name: str = "Unnamed Test"
    test_category: str = "functional"
    priority: str = "medium"
    description: Optional[str] = None
    preconditions: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    suite_name: str = ""

    # Test definition
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    expected_result: str = ""
    selenium_code: Optional[str] = None

    # Destructive flag
    is_destructive: bool = False
    destructive_reason: Optional[str] = None

    # Execution results
    status: GeneratedTestStatus = GeneratedTestStatus.PENDING
    steps_results: List[Dict[str, Any]] = Field(default_factory=list)
    actual_result: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    execution_time_ms: Optional[int] = None
    console_logs: List[Dict[str, Any]] = Field(default_factory=list)
    failure_analysis: Optional[Dict[str, Any]] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["status"] = self.status.value
        for k in ("created_at", "executed_at"):
            if isinstance(doc.get(k), datetime):
                doc[k] = doc[k].replace(tzinfo=None)
        return doc


# ============================================
# Welcome Message Builder
# ============================================

def create_welcome_message(session_id: str, project_name: str = "", base_url: str = "") -> dict:
    """Create the initial welcome message for a chat session."""
    content = f"Welcome to **TestPilot AI**"
    if project_name:
        content += f" for **{project_name}**"
    content += ".\n\n"

    if base_url:
        content += (
            f"Target: `{base_url}`\n\n"
            f"**Testing Flow:**\n"
            f"1. Enter a URL and click Analyze -- I will open a browser and inspect the page\n"
            f"2. If login is required, log in directly in the browser window that opens\n"
            f"3. Type **done** when you have finished logging in\n"
            f"4. Click **Generate Tests** -- I will create comprehensive Selenium test code\n"
            f"5. Review tests -- approve any that modify data (add/edit/delete)\n"
            f"6. Click **Run Tests** -- I will execute everything and generate a detailed report\n\n"
            f"You can ask me questions about testing at any time."
        )
    else:
        content += "Enter a URL to get started, or ask me anything about web testing."

    msg = ChatMessageDocument(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=content,
        message_type=MessageType.TEXT,
    )
    return msg.to_mongo()