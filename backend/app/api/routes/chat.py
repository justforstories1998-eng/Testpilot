"""
TestPilot Chat Routes — Conversational Multi-Page Workflow & TSV Parsing
========================================================================
"""

from __future__ import annotations

import asyncio
import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from urllib.parse import urlparse

from fastapi import (
    APIRouter, HTTPException, WebSocket,
    WebSocketDisconnect, Query,
)
from fastapi.responses import FileResponse
from bson import ObjectId
from bson.errors import InvalidId

from app.config import get_settings
from app.database import (
    chat_sessions_collection,
    chat_messages_collection,
    generated_tests_collection,
    projects_collection,
)
from app.models.chat import (
    ChatSessionDocument,
    ChatMessageDocument,
    GeneratedTestDocument,
    MessageRole,
    MessageType,
    SessionState,
    create_welcome_message,
)
from app.schemas.chat import (
    SendMessageRequest,
    GenerateTestsRequest,
    ExecuteTestsRequest,
    AnalyzeUrlRequest,
    AnalyzeUrlResponse,
    ApproveTestsRequest,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionListItem,
    GeneratedTestResponse,
    TestGenerationResponse,
    TestExecutionResponse,
)

# ── Playwright manager aliased as browser_manager for drop-in replacement ──
from app.services.playwright_manager import playwright_manager as browser_manager

logger = logging.getLogger("testpilot.api.chat")

router = APIRouter()
ws_router = APIRouter(tags=["AI Chat WebSocket"])


# ============================================
# Helpers
# ============================================

def _oid(s: str) -> ObjectId:
    try:
        return ObjectId(s)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid ID: {s}")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _screenshot_url(path: str) -> str:
    if not path:
        return ""
    return f"/static/screenshots/{os.path.basename(path)}"


# ============================================
# Core Navigation Logic
# ============================================

async def _process_url_analysis(session_id: str, url: str) -> dict:
    """Navigate to URL using Playwright, take screenshot, detect login state."""
    settings = get_settings()
    try:
        def _nav():
            ps = browser_manager.get_or_create(
                session_id,
                headless=settings.PLAYWRIGHT_HEADLESS,
                force_restart=True,
            )
            html = ps.navigate(url, wait_seconds=3.0)
            screenshot = ps.take_screenshot("initial_page")
            return html, screenshot, ps

        html, screenshot, ps = await asyncio.to_thread(_nav)
    except Exception as e:
        err_msg = str(e) or repr(e) or type(e).__name__
        logger.warning(
            f"[{session_id[:8]}] Initial analysis failed: {repr(e)}"
        )
        try:
            def _nav_headless():
                ps = browser_manager.get_or_create(
                    session_id, headless=True, force_restart=True
                )
                html = ps.navigate(url, wait_seconds=3.0)
                screenshot = ps.take_screenshot("initial_page")
                return html, screenshot, ps

            html, screenshot, ps = await asyncio.to_thread(_nav_headless)
        except Exception as e2:
            err_msg = str(e2) or repr(e2) or type(e2).__name__
            logger.exception(
                f"URL analysis failed for session {session_id} and url {url}: {repr(e2)}"
            )
            browser_manager.close_session(session_id)
            return {"error": err_msg}
    login_info = {
        "is_login_page": False,
        "confidence": 0,
        "page_type": "unknown",
        "page_title": ps.page_title or "",
    }

    if settings.groq_configured:
        try:
            from app.services.groq_service import groq_service
            login_info = await asyncio.to_thread(
                groq_service.detect_login_page, html, url
            )
        except Exception as e:
            logger.warning(f"Login detection failed: {e}")

    is_login = (
        login_info.get("is_login_page", False)
        and login_info.get("confidence", 0) > 0.5
    )
    page_type = login_info.get("page_type", "unknown")
    page_title = login_info.get("page_title", ps.page_title or "")
    new_state = SessionState.WAITING_LOGIN if is_login else SessionState.READY_TO_GENERATE

    page_analysis = None
    if not is_login and settings.groq_configured:
        try:
            from app.services.groq_service import groq_service
            page_analysis = await asyncio.to_thread(
                groq_service.analyze_page, html, url
            )
        except Exception as e:
            logger.warning(f"Page analysis failed: {e}")

    ps.login_required = is_login
    final_url = ps.current_url or url

    if is_login:
        msg_content = (
            f"**Page analyzed:** `{final_url}`\n"
            f"**Type:** {page_type} | **Title:** {page_title}\n\n"
            f"**Login page detected** (confidence: {login_info.get('confidence', 0):.0%})\n\n"
            f"A browser window has opened. Please log in directly in the browser.\n\n"
            f"**When you are done logging in, type `done` here.**"
        )
    else:
        features_str = ""
        if page_analysis:
            features = page_analysis.get("key_features", [])[:5]
            if features:
                features_str = "\n**Features:** " + ", ".join(features)

        msg_content = (
            f"**Page analyzed:** `{final_url}`\n"
            f"**Type:** {page_type} | **Title:** {page_title}\n"
            f"**Page size:** {len(html):,} characters"
            f"{features_str}\n\n"
            f"No login required. Click **Generate Tests** to proceed."
        )

    return {
        "html": html,
        "screenshot": screenshot,
        "login_info": login_info,
        "is_login": is_login,
        "page_type": page_type,
        "page_title": page_title,
        "new_state": new_state.value,
        "page_analysis": page_analysis,
        "msg_content": msg_content,
        "final_url": final_url,
    }


async def _handle_move_to_next_page(session_id: str, next_url: str) -> str:
    """Handles the user saying 'yes' to testing the next queued URL."""
    sessions_col = chat_sessions_collection()
    oid = ObjectId(session_id)

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {
            "state": SessionState.ANALYZING.value,
            "next_proposed_url": None,
        }},
    )

    res = await _process_url_analysis(session_id, next_url)

    if "error" in res:
        await sessions_col.update_one(
            {"_id": oid},
            {"$set": {"state": SessionState.IDLE.value}},
        )
        return f"Failed to navigate to {next_url}: {res['error']}"

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {
            "target_url": res["final_url"],
            "state": SessionState.READY_TO_GENERATE.value,
            "page_analysis": res["page_analysis"],
            "updated_at": _now(),
        }},
    )

    parsed_path = urlparse(res["final_url"]).path or res["final_url"]
    return (
        f"Successfully moved to `{parsed_path}`.\n\n"
        f"I have scanned this page and captured its background APIs. "
        f"Click **Generate Tests** to create the test suite specifically for this page."
    )


# ============================================
# Basic Session Endpoints
# ============================================

@router.get("/status")
async def chat_status():
    """Check Groq AI configuration and browser status."""
    settings = get_settings()
    return {
        "groq_configured": settings.groq_configured,
        "model": settings.GROQ_MODEL if settings.groq_configured else None,
        "active_browsers": browser_manager.active_count,
    }


@router.get("/sessions/active", response_model=ChatSessionResponse)
async def get_or_create_active_session(project_id: str = Query(...)):
    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()

    session = await sessions_col.find_one(
        {"project_id": project_id, "is_active": True},
        sort=[("updated_at", -1)],
    )

    if session:
        session_id = str(session["_id"])
        messages = await messages_col.find(
            {"session_id": session_id}
        ).sort("created_at", 1).to_list(length=1000)
        return ChatSessionResponse.from_mongo_doc(session, messages)

    project_name = ""
    base_url = ""
    try:
        project = await projects_collection().find_one(
            {"_id": ObjectId(project_id)}
        )
        if project:
            project_name = project.get("name", "")
            base_url = project.get("base_url", "")
    except Exception:
        pass

    session_doc = ChatSessionDocument(
        project_id=project_id,
        title=f"Test: {base_url}" if base_url else "New Chat",
        target_url=base_url or None,
    )
    result = await sessions_col.insert_one(session_doc.to_mongo())
    session_id = str(result.inserted_id)

    welcome = create_welcome_message(session_id, project_name, base_url)
    await messages_col.insert_one(welcome)

    session = await sessions_col.find_one({"_id": result.inserted_id})
    messages = await messages_col.find(
        {"session_id": session_id}
    ).sort("created_at", 1).to_list(length=100)

    return ChatSessionResponse.from_mongo_doc(session, messages)


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_new_session(
    project_id: str = Query(...),
    target_url: Optional[str] = Query(None),
):
    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()

    await sessions_col.update_many(
        {"project_id": project_id, "is_active": True},
        {"$set": {"is_active": False, "updated_at": _now()}},
    )

    project_name = ""
    base_url = target_url or ""
    try:
        project = await projects_collection().find_one(
            {"_id": ObjectId(project_id)}
        )
        if project:
            project_name = project.get("name", "")
            if not base_url:
                base_url = project.get("base_url", "")
    except Exception:
        pass

    session_doc = ChatSessionDocument(
        project_id=project_id,
        title=f"Test: {base_url}" if base_url else "New Chat",
        target_url=base_url or None,
    )
    result = await sessions_col.insert_one(session_doc.to_mongo())
    session_id = str(result.inserted_id)

    welcome = create_welcome_message(session_id, project_name, base_url)
    await messages_col.insert_one(welcome)

    session = await sessions_col.find_one({"_id": result.inserted_id})
    messages = await messages_col.find(
        {"session_id": session_id}
    ).sort("created_at", 1).to_list(length=100)

    return ChatSessionResponse.from_mongo_doc(session, messages)


@router.get("/sessions", response_model=List[ChatSessionListItem])
async def list_sessions(
    project_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
):
    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()

    cursor = (
        sessions_col.find({"project_id": project_id})
        .sort("updated_at", -1)
        .limit(limit)
    )
    result = []
    async for s in cursor:
        sid = str(s["_id"])
        count = await messages_col.count_documents({"session_id": sid})
        result.append(ChatSessionListItem.from_mongo_doc(s, count))
    return result


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(session_id: str):
    oid = _oid(session_id)
    session = await chat_sessions_collection().find_one({"_id": oid})
    if not session:
        raise HTTPException(404, "Session not found")

    messages = await chat_messages_collection().find(
        {"session_id": session_id}
    ).sort("created_at", 1).to_list(length=1000)
    return ChatSessionResponse.from_mongo_doc(session, messages)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    oid = _oid(session_id)
    result = await chat_sessions_collection().update_one(
        {"_id": oid},
        {"$set": {"is_active": False, "updated_at": _now()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Session not found")

    try:
        browser_manager.close_session(session_id)
    except Exception:
        pass

    return {"message": "Session deleted", "session_id": session_id}


# ============================================
# Post-Login Handler
# ============================================

async def _handle_login_complete(session_id: str, session: dict) -> str:
    """Handle when user says done after logging in."""
    sessions_col = chat_sessions_collection()

    ps = browser_manager.get(session_id)
    if not ps or not ps.is_running:
        return (
            "No active browser session found. "
            "Please paste a URL first to open a browser."
        )

    try:
        html = await asyncio.to_thread(ps.get_current_html)
        state = await asyncio.to_thread(ps.get_current_state)
        await asyncio.to_thread(ps.take_screenshot, "post_login")
    except Exception as e:
        return f"Error capturing page after login: {str(e)}"

    if not html or len(html) < 100:
        return (
            "The page appears empty. Make sure you are logged in and on the "
            "main page, then type **done** again."
        )

    ps.is_logged_in = True
    ps.page_html = html
    current_url = state.get("url", "unknown")

    page_info = ""
    analysis = None
    settings = get_settings()

    if settings.groq_configured:
        try:
            from app.services.groq_service import groq_service
            analysis = await asyncio.to_thread(
                groq_service.analyze_page, html, current_url
            )
            interactive = await asyncio.to_thread(
                ps.get_page_interactive_elements
            )
            page_info = (
                f"\n\n**Page Analysis:**\n"
                f"- Type: {analysis.get('page_type', 'unknown')}\n"
                f"- Features: {', '.join(analysis.get('key_features', [])[:5])}\n"
                f"- Buttons found: {interactive.get('total_buttons', 0)}\n"
                f"- Forms found: {interactive.get('total_forms', 0)}"
            )
        except Exception as e:
            logger.warning(f"Post-login analysis failed: {e}")

    await sessions_col.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {
            "state": "ready",
            "login_completed": True,
            "target_url": current_url,
            "page_analysis": analysis,
            "updated_at": _now(),
        }},
    )

    return (
        f"Login confirmed. Authenticated page captured.\n\n"
        f"**Current page:** `{current_url}`\n"
        f"**Title:** {state.get('title', 'N/A')}\n"
        f"**Page size:** {len(html):,} characters"
        f"{page_info}\n\n"
        f"Click **Generate Tests** to crawl this dashboard and create "
        f"comprehensive Selenium tests."
    )


async def _handle_targeted_test(
    session_id: str, session: dict, instruction: str
) -> str:
    from app.services.groq_service import groq_service

    ps = browser_manager.get(session_id)
    html = ""
    interactive = {}

    if ps and ps.is_running:
        try:
            html = await asyncio.to_thread(ps.get_current_html)
            interactive = await asyncio.to_thread(
                ps.get_page_interactive_elements
            )
        except Exception:
            pass

    if not html:
        return (
            "I need an active browser session to generate targeted tests. "
            "Please paste a URL first."
        )

    target_url = session.get("target_url", "")

    try:
        test_data = await asyncio.to_thread(
            groq_service.generate_targeted_test,
            instruction, html, target_url, interactive,
        )
    except Exception as e:
        return f"Could not generate targeted test: {str(e)}"

    gen_tests_col = generated_tests_collection()
    test_doc = GeneratedTestDocument(
        session_id=session_id,
        project_id=session.get("project_id", ""),
        test_name=test_data.get("test_name", "Custom Test"),
        test_category=test_data.get("category", "functional"),
        priority=test_data.get("priority", "high"),
        description=test_data.get("description", instruction),
        selenium_code=test_data.get("selenium_code", ""),
        expected_result=test_data.get("expected_result", ""),
        is_destructive=test_data.get("is_destructive", False),
        destructive_reason=test_data.get("destructive_reason"),
    )
    await gen_tests_col.insert_one(test_doc.to_mongo())

    try:
        from app.services.test_executor import SeleniumTestExecutor

        executor = SeleniumTestExecutor(session_id)
        # Re-use the existing Playwright-driven driver if available
        existing_driver = ps.driver if (ps and ps.is_running) else None
        if existing_driver:
            executor.driver = existing_driver

        test_to_run = {
            "test_id": "TC_CUSTOM",
            "test_name": test_data.get("test_name", "Custom Test"),
            "selenium_code": test_data.get("selenium_code", ""),
            "description": test_data.get("description", ""),
            "category": "functional",
            "priority": "high",
            "is_destructive": test_data.get("is_destructive", False),
            "expected_result": test_data.get("expected_result", ""),
        }

        result = await asyncio.to_thread(
            executor._execute_single_test, test_to_run, target_url
        )

        status = result.get("status", "error")
        actual = result.get("actual_result", "")
        error = result.get("error_message", "")

        if status == "passed":
            return (
                f"**Custom Test: {test_data.get('test_name', 'Test')}**\n\n"
                f"**Result: PASSED**\n\n{actual}"
            )
        return (
            f"**Custom Test: {test_data.get('test_name', 'Test')}**\n\n"
            f"**Result: {status.upper()}**\n\n"
            f"Error: {error}\n\nResult: {actual}"
        )
    except Exception as e:
        return (
            f"**Test Generated:** {test_data.get('test_name', 'Custom Test')}\n\n"
            f"Could not run automatically: {str(e)}"
        )


async def _handle_chat(
    session_id: str, session: dict, messages_col
) -> str:
    history_docs = await messages_col.find(
        {"session_id": session_id}
    ).sort("created_at", 1).to_list(length=50)
    history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in history_docs
    ]
    try:
        from app.services.groq_service import groq_service
        return await asyncio.to_thread(
            groq_service.chat, history, session.get("target_url")
        )
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================
# POST /send — Smart message handler
# ============================================

@router.post("/send", response_model=ChatMessageResponse)
async def send_message(req: SendMessageRequest):
    settings = get_settings()
    if not settings.groq_configured:
        raise HTTPException(503, "Groq AI not configured")

    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()
    oid = _oid(req.session_id)
    session = await sessions_col.find_one({"_id": oid})
    if not session:
        raise HTTPException(404, "Session not found")

    user_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.USER,
        content=req.content,
        message_type=MessageType.TEXT,
    )
    await messages_col.insert_one(user_msg.to_mongo())

    content_lower = req.content.strip().lower()
    current_state = session.get("state", "idle")

    # 1. URL Interceptor
    if content_lower.startswith("http://") or content_lower.startswith("https://"):
        url = req.content.strip().split()[0]

        await sessions_col.update_one(
            {"_id": oid},
            {"$set": {"state": SessionState.ANALYZING.value}},
        )
        res = await _process_url_analysis(req.session_id, url)

        if "error" in res:
            err_msg = res['error'] or 'Unknown browser error'
            ai_content = f"Cannot access URL: {err_msg}"
            await sessions_col.update_one(
                {"_id": oid},
                {"$set": {"state": SessionState.IDLE.value}},
            )
        else:
            await sessions_col.update_one(
                {"_id": oid},
                {"$set": {
                    "target_url": res["final_url"],
                    "state": res["new_state"],
                    "login_required": res["is_login"],
                    "login_completed": False,
                    "browser_session_active": True,
                    "page_analysis": res["page_analysis"],
                    "updated_at": _now(),
                }},
            )
            ai_content = res["msg_content"]

    # 2. Accept Next Page
    elif (
        any(w in content_lower for w in [
            "yes", "sure", "move on", "next", "ok",
            "do it", "please", "yep", "yeah", "y",
        ])
        and session.get("next_proposed_url")
    ):
        next_url = session.get("next_proposed_url")
        ai_content = await _handle_move_to_next_page(req.session_id, next_url)

    # 3. Handle Login Complete
    elif (
        content_lower in {
            "done", "done.", "i'm done", "im done",
            "login done", "logged in", "i have logged in", "login complete",
        }
        and current_state == "waiting_login"
    ):
        ai_content = await _handle_login_complete(req.session_id, session)

    # 4. Decline Next Page
    elif (
        any(w in content_lower for w in [
            "no", "stop", "don't", "dont", "nah", "cancel",
        ])
        and session.get("next_proposed_url")
    ):
        await sessions_col.update_one(
            {"_id": oid},
            {"$set": {"next_proposed_url": None}},
        )
        ai_content = (
            "Okay! We will stay on the current page. "
            "Let me know what you'd like to test next."
        )

    # 5. Standard Intent / Chat
    else:
        from app.services.groq_service import groq_service
        intent = groq_service.detect_test_intent(req.content)

        if intent["is_run_request"] and current_state in (
            "tests_ready", "awaiting_approval"
        ):
            ai_content = (
                "Starting test execution... "
                "Click the **Run Tests** button above to proceed."
            )
            await sessions_col.update_one(
                {"_id": oid},
                {"$set": {"state": "tests_ready", "updated_at": _now()}},
            )

        elif intent["is_generate_request"] and current_state in (
            "ready", "login_done", "completed", "idle"
        ):
            if session.get("target_url"):
                ai_content = (
                    "Ready to generate tests. "
                    "Click the **Generate Tests** button above to proceed."
                )
            else:
                ai_content = (
                    "Please paste a URL first, then I can generate tests."
                )

        elif (
            intent["is_test_request"]
            and session.get("target_url")
            and session.get("browser_session_active")
        ):
            ai_content = await _handle_targeted_test(
                req.session_id, session, req.content
            )

        else:
            ai_content = await _handle_chat(
                req.session_id, session, messages_col
            )

    ai_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.ASSISTANT,
        content=ai_content,
        message_type=MessageType.TEXT,
    )
    ai_result = await messages_col.insert_one(ai_msg.to_mongo())
    await sessions_col.update_one(
        {"_id": oid}, {"$set": {"updated_at": _now()}}
    )

    updated_session = await sessions_col.find_one({"_id": oid})
    current_state_now = (
        updated_session.get("state", "idle") if updated_session else "idle"
    )

    saved = await messages_col.find_one({"_id": ai_result.inserted_id})
    return ChatMessageResponse.from_mongo_doc(
        saved, session_state=current_state_now
    )


# ============================================
# POST /analyze-url
# ============================================

@router.post("/analyze-url", response_model=AnalyzeUrlResponse)
async def analyze_url(req: AnalyzeUrlRequest):
    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()
    oid = _oid(req.session_id)

    session = await sessions_col.find_one({"_id": oid})
    if not session:
        raise HTTPException(404, "Session not found")

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {
            "target_url": req.url,
            "state": SessionState.ANALYZING.value,
            "updated_at": _now(),
        }},
    )

    user_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.USER,
        content=f"Analyze URL: {req.url}",
    )
    await messages_col.insert_one(user_msg.to_mongo())

    res = await _process_url_analysis(req.session_id, req.url)

    if "error" in res:
        err_text = res['error'] or 'Unknown browser error'
        browser_manager.close_session(req.session_id)
        err_msg = ChatMessageDocument(
            session_id=req.session_id,
            role=MessageRole.ASSISTANT,
            content=f"Cannot access URL: {err_text}",
            message_type=MessageType.ERROR,
        )
        await messages_col.insert_one(err_msg.to_mongo())
        await sessions_col.update_one(
            {"_id": oid},
            {"$set": {"state": SessionState.IDLE.value}},
        )
        raise HTTPException(400, f"Cannot access URL: {err_text}")

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {
            "state": res["new_state"],
            "login_required": res["is_login"],
            "login_completed": False,
            "browser_session_active": True,
            "page_analysis": res["page_analysis"],
            "updated_at": _now(),
        }},
    )

    ai_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.ASSISTANT,
        content=res["msg_content"],
        message_type=MessageType.TEXT,
        metadata={"login_info": res["login_info"]},
    )
    await messages_col.insert_one(ai_msg.to_mongo())

    return {
        "session_id": req.session_id,
        "url": res["final_url"],
        "state": res["new_state"],
        "is_login_page": res["is_login"],
        "confidence": res["login_info"].get("confidence", 0),
        "page_type": res["page_type"],
        "page_title": res["page_title"],
        "screenshot": (
            _screenshot_url(res["screenshot"]) if res["screenshot"] else None
        ),
    }


# ============================================
# POST /generate-tests
# ============================================

@router.post("/generate-tests", response_model=TestGenerationResponse)
async def generate_tests(req: GenerateTestsRequest):
    settings = get_settings()
    if not settings.groq_configured:
        raise HTTPException(503, "Groq AI not configured")

    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()
    gen_tests_col = generated_tests_collection()

    oid = _oid(req.session_id)
    session = await sessions_col.find_one({"_id": oid})
    if not session:
        raise HTTPException(404, "Session not found")

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {"state": SessionState.GENERATING.value, "updated_at": _now()}},
    )

    user_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.USER,
        content="Generate tests for current page.",
    )
    await messages_col.insert_one(user_msg.to_mongo())

    html_content = req.html_content
    interactive_elements: Dict[str, Any] = {}
    apis: List[Any] = []
    untested_links = session.get("untested_links", [])

    ps = browser_manager.get(req.session_id)
    start_url = (
        ps.current_url
        if (ps and ps.is_running and ps.current_url)
        else req.url
    )

    if ps and ps.is_running:
        if not html_content:
            html_content = ps.get_current_html()

        try:
            interactive_elements = await asyncio.to_thread(
                ps.get_page_interactive_elements
            )
        except Exception:
            pass

        try:
            apis = await asyncio.to_thread(ps.get_page_apis)
        except Exception:
            pass

        try:
            new_links = await asyncio.to_thread(ps.get_navigable_links)
            for link in new_links:
                if link not in untested_links:
                    untested_links.append(link)
            await sessions_col.update_one(
                {"_id": oid},
                {"$set": {"untested_links": untested_links}},
            )
        except Exception as e:
            logger.warning(f"Link extraction failed: {e}")

    if not html_content:
        try:
            def _fetch():
                tmp = browser_manager.get_or_create(
                    req.session_id, headless=True
                )
                return tmp.navigate(start_url, 2.5)

            html_content = await asyncio.to_thread(_fetch)
        except Exception as e:
            raise HTTPException(400, f"Cannot access URL: {str(e)}")

    page_analysis = session.get("page_analysis")
    if not page_analysis:
        try:
            from app.services.groq_service import groq_service
            page_analysis = await asyncio.to_thread(
                groq_service.analyze_page, html_content, start_url
            )
            await sessions_col.update_one(
                {"_id": oid},
                {"$set": {"page_analysis": page_analysis}},
            )
        except Exception:
            page_analysis = {}

    try:
        from app.services.groq_service import groq_service
        ai_result = await asyncio.to_thread(
            groq_service.generate_selenium_tests,
            start_url,
            html_content,
            page_analysis,
            req.additional_instructions,
            interactive_elements if interactive_elements else None,
            apis if apis else None,
        )
    except Exception as e:
        await sessions_col.update_one(
            {"_id": oid}, {"$set": {"state": "ready"}}
        )
        raise HTTPException(500, f"Test generation failed: {str(e)}")

    if not ai_result or not ai_result.get("test_suites"):
        await sessions_col.update_one(
            {"_id": oid}, {"$set": {"state": "ready"}}
        )
        msg = (
            "AI failed to generate tests (likely due to token limits). "
            "Please provide a more specific prompt or try again."
        )
        await messages_col.insert_one(
            ChatMessageDocument(
                session_id=req.session_id,
                role=MessageRole.ASSISTANT,
                content=msg,
            ).to_mongo()
        )
        return TestGenerationResponse(
            session_id=req.session_id,
            page_analysis=page_analysis,
            test_cases=[],
            total_tests=0,
        )

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {
            "test_generation_data": ai_result,
            "updated_at": _now(),
        }},
    )
    await gen_tests_col.delete_many({"session_id": req.session_id})

    saved_tests: List[GeneratedTestResponse] = []
    destructive_count = 0
    project_id = session.get("project_id", "")

    for suite in ai_result.get("test_suites", []):
        suite_name = suite.get("suite_name", "")
        for tc in suite.get("tests", []):
            is_destructive = tc.get("is_destructive", False)
            if is_destructive:
                destructive_count += 1

            test_doc = GeneratedTestDocument(
                session_id=req.session_id,
                project_id=project_id,
                test_name=tc.get("test_name", "Unnamed"),
                test_category=tc.get("category", "functional"),
                priority=tc.get("priority", "medium"),
                description=tc.get("description", ""),
                preconditions=tc.get("preconditions", []),
                tags=tc.get("tags", []),
                suite_name=suite_name,
                steps=tc.get("steps", []),
                expected_result=tc.get("expected_result", ""),
                selenium_code=tc.get("selenium_code", ""),
                is_destructive=is_destructive,
                destructive_reason=tc.get("destructive_reason"),
            )
            insert_result = await gen_tests_col.insert_one(
                test_doc.to_mongo()
            )
            saved_doc = await gen_tests_col.find_one(
                {"_id": insert_result.inserted_id}
            )
            saved_tests.append(GeneratedTestResponse.from_mongo_doc(saved_doc))

    total_tests = len(saved_tests)
    new_state = (
        "awaiting_approval" if destructive_count > 0 else "tests_ready"
    )

    await sessions_col.update_one(
        {"_id": oid},
        {"$set": {
            "state": new_state,
            "total_tests": total_tests,
            "updated_at": _now(),
        }},
    )

    summary = (
        f"**Generated {total_tests} Selenium test cases** for `{start_url}`\n"
    )

    if destructive_count > 0:
        summary += (
            f"**{destructive_count} test(s) modify data** "
            f"-- these need your approval.\n\n"
        )

    ado_plan = ai_result.get("ado_test_plan")
    if ado_plan:
        summary += (
            f"\n**Test Plan (Copy directly into Excel / Azure DevOps):**\n"
            f"```text\n{ado_plan}\n```\n\n"
        )

    summary += "\nClick **Run Tests** to execute all tests in the background."

    ai_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.ASSISTANT,
        content=summary,
        message_type=MessageType.TEST_RESULT,
        metadata={
            "test_count": total_tests,
            "destructive_count": destructive_count,
        },
    )
    await messages_col.insert_one(ai_msg.to_mongo())

    return TestGenerationResponse(
        session_id=req.session_id,
        page_analysis=page_analysis,
        test_cases=saved_tests,
        total_tests=total_tests,
    )


# ============================================
# POST /execute-tests
# ============================================

@router.post("/execute-tests", response_model=TestExecutionResponse)
async def execute_tests(req: ExecuteTestsRequest):
    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()
    gen_tests_col = generated_tests_collection()

    session_oid = _oid(req.session_id)
    session = await sessions_col.find_one({"_id": session_oid})
    if not session:
        raise HTTPException(404, "Session not found")

    test_data = session.get("test_generation_data")
    if not test_data:
        raise HTTPException(404, "No tests found. Generate tests first.")

    await sessions_col.update_one(
        {"_id": session_oid},
        {"$set": {
            "state": SessionState.EXECUTING.value,
            "updated_at": _now(),
        }},
    )

    start_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.ASSISTANT,
        content="Running Selenium tests...",
        message_type=MessageType.STATUS,
    )
    await messages_col.insert_one(start_msg.to_mongo())

    ps = browser_manager.get(req.session_id)
    existing_driver = (
        ps.driver if (ps and ps.is_running and ps.is_logged_in) else None
    )

    approved_ids = set(req.approved_destructive_ids or [])

    try:
        from app.services.test_executor import execute_tests_for_session
        target_url = session.get("target_url", "")
        results = await asyncio.to_thread(
            execute_tests_for_session,
            req.session_id,
            test_data,
            target_url,
            approved_destructive_ids=approved_ids,
            skip_destructive=req.skip_destructive,
            existing_driver=existing_driver,
        )
    except Exception as e:
        await sessions_col.update_one(
            {"_id": session_oid},
            {"$set": {"state": "tests_ready"}},
        )
        raise HTTPException(500, f"Execution failed: {str(e)}")

    settings = get_settings()
    failure_analyses: List[Dict[str, Any]] = []
    if settings.groq_configured:
        for tr in results.get("test_results", []):
            if tr.get("status") in ("failed", "error"):
                try:
                    from app.services.groq_service import groq_service
                    analysis = await asyncio.to_thread(
                        groq_service.analyze_failure,
                        tr.get("test_name", ""),
                        tr.get("description", ""),
                        tr.get("selenium_code", ""),
                        tr.get("error_message", "Unknown"),
                        tr.get("steps", []),
                    )
                    failure_analyses.append(analysis)
                    tr["failure_analysis"] = analysis
                except Exception:
                    failure_analyses.append({})

    test_docs = await gen_tests_col.find(
        {"session_id": req.session_id}
    ).sort("created_at", 1).to_list(length=200)

    for tr in results.get("test_results", []):
        for doc in test_docs:
            if doc.get("test_name") == tr.get("test_name"):
                await gen_tests_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "status": tr["status"],
                        "actual_result": tr.get("actual_result", ""),
                        "error_message": tr.get("error_message"),
                        "screenshot_path": tr.get("screenshot"),
                        "execution_time_ms": tr.get("execution_time_ms", 0),
                        "steps_results": tr.get("steps", []),
                        "console_logs": tr.get("console_logs", []),
                        "failure_analysis": tr.get("failure_analysis"),
                        "executed_at": _now(),
                    }},
                )
                break

    report_path: Optional[str] = None
    try:
        from app.services.report_generator import report_generator
        project_name = "TestPilot"
        try:
            proj = await projects_collection().find_one(
                {"_id": ObjectId(session.get("project_id", ""))}
            )
            if proj:
                project_name = proj.get("name", "TestPilot")
        except Exception:
            pass

        report_path = await asyncio.to_thread(
            report_generator.generate,
            req.session_id,
            project_name,
            session.get("target_url", ""),
            results,
            failure_analyses or None,
            session.get("page_analysis"),
        )
    except Exception as e:
        logger.error(f"Report generation failed: {e}")

    pass_rate = results.get("pass_rate", 0)

    # ------------------------------------------------------------------
    # Conversational Link Queue Logic
    # ------------------------------------------------------------------
    current_url = session.get("target_url", "")
    untested_links = session.get("untested_links", [])

    untested_links = [
        u for u in untested_links
        if u.rstrip("/") != current_url.rstrip("/")
    ]

    next_proposed_url = None
    if untested_links:
        next_proposed_url = untested_links[0]
        untested_links = untested_links[1:]

    await sessions_col.update_one(
        {"_id": session_oid},
        {"$set": {
            "state": SessionState.COMPLETED.value,
            "total_tests": results.get("total", 0),
            "passed_tests": results.get("passed", 0),
            "failed_tests": results.get("failed", 0),
            "last_report_path": report_path,
            "untested_links": untested_links,
            "next_proposed_url": next_proposed_url,
            "updated_at": _now(),
        }},
    )

    try:
        await projects_collection().update_one(
            {"_id": ObjectId(session.get("project_id", ""))},
            {
                "$set": {
                    "last_test_at": _now(),
                    "last_pass_rate": pass_rate,
                    "updated_at": _now(),
                },
                "$inc": {"total_sessions": 1},
            },
        )
    except Exception:
        pass

    exec_time = results.get("execution_time_ms", 0) / 1000
    status_label = (
        "PASS" if pass_rate >= 90
        else ("PARTIAL" if pass_rate >= 50 else "FAIL")
    )

    completion = (
        f"**Test Execution Complete -- {status_label}**\n\n"
        f"**Results:**\n"
        f"  - Total: {results.get('total', 0)}\n"
        f"  - Passed: {results.get('passed', 0)}\n"
        f"  - Failed: {results.get('failed', 0)}\n"
        f"  - Errors: {results.get('errors', 0)}\n"
        f"  - Skipped: {results.get('skipped', 0)}\n"
        f"  - Pass Rate: {pass_rate}%\n"
        f"  - Duration: {exec_time:.1f}s\n\n"
    )

    if report_path:
        completion += (
            "**Report generated** -- click Download Report to get the "
            "Excel file.\n\n"
        )
    if failure_analyses:
        completion += (
            f"**AI analyzed {len(failure_analyses)} failure(s)** "
            f"with root-cause analysis.\n\n"
        )

    dp = results.get("destructive_pending", [])
    if dp:
        completion += (
            f"**{len(dp)} destructive test(s) skipped** -- approve to run:\n"
        )
        for d in dp:
            completion += f"  - `{d['test_name']}` -- {d['reason']}\n\n"

    if next_proposed_url:
        parsed_current = urlparse(current_url).path or current_url
        parsed_next = urlparse(next_proposed_url).path or next_proposed_url
        completion += (
            f"---\n\n"
            f"**I have finished testing the `{parsed_current}` page.**\n\n"
            f"Do you want me to move on to the `{parsed_next}` page and "
            f"crawl it for functionality and API testing? "
            f"(Type **yes** or **no**)"
        )

    comp_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.ASSISTANT,
        content=completion,
        message_type=MessageType.REPORT,
        metadata={
            "report_path": report_path,
            "results_summary": {
                "total": results.get("total", 0),
                "passed": results.get("passed", 0),
                "failed": results.get("failed", 0),
                "pass_rate": pass_rate,
            },
        },
    )
    await messages_col.insert_one(comp_msg.to_mongo())

    updated_docs = await gen_tests_col.find(
        {"session_id": req.session_id}
    ).sort("created_at", 1).to_list(length=200)

    return TestExecutionResponse(
        session_id=req.session_id,
        total_tests=results.get("total", 0),
        passed=results.get("passed", 0),
        failed=results.get("failed", 0),
        errors=results.get("errors", 0),
        skipped=results.get("skipped", 0),
        pass_rate=pass_rate,
        execution_time_ms=results.get("execution_time_ms", 0),
        report_path=report_path,
        tests=[GeneratedTestResponse.from_mongo_doc(d) for d in updated_docs],
    )


# ============================================
# POST /approve-and-run
# ============================================

@router.post("/approve-and-run")
async def approve_and_run(req: ApproveTestsRequest):
    sessions_col = chat_sessions_collection()
    messages_col = chat_messages_collection()
    gen_tests_col = generated_tests_collection()

    session = await sessions_col.find_one({"_id": _oid(req.session_id)})
    if not session:
        raise HTTPException(404, "Session not found")

    test_data = session.get("test_generation_data")
    if not test_data:
        raise HTTPException(404, "No test data found")

    approved_set = set(req.approved_test_ids)
    filtered_data: Dict[str, Any] = {"test_suites": []}

    for suite in test_data.get("test_suites", []):
        filtered = [
            t for t in suite.get("tests", [])
            if t.get("test_id") in approved_set
        ]
        if filtered:
            filtered_data["test_suites"].append({
                "suite_name": suite.get("suite_name", "Approved"),
                "tests": filtered,
            })

    if not filtered_data["test_suites"]:
        raise HTTPException(404, "No matching tests found")

    user_msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.USER,
        content=f"Approved {len(approved_set)} destructive test(s).",
    )
    await messages_col.insert_one(user_msg.to_mongo())

    from app.services.test_executor import execute_tests_for_session

    ps = browser_manager.get(req.session_id)
    existing_driver = (
        ps.driver if (ps and ps.is_running and ps.is_logged_in) else None
    )

    results = await asyncio.to_thread(
        execute_tests_for_session,
        req.session_id,
        filtered_data,
        session.get("target_url", ""),
        approved_destructive_ids=approved_set,
        skip_destructive=False,
        existing_driver=existing_driver,
    )

    for tr in results.get("test_results", []):
        docs = await gen_tests_col.find(
            {"session_id": req.session_id}
        ).to_list(200)
        for doc in docs:
            if doc.get("test_name") == tr.get("test_name"):
                await gen_tests_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "status": tr["status"],
                        "actual_result": tr.get("actual_result", ""),
                        "error_message": tr.get("error_message"),
                        "screenshot_path": tr.get("screenshot"),
                        "execution_time_ms": tr.get("execution_time_ms", 0),
                        "executed_at": _now(),
                    }},
                )
                break

    msg = ChatMessageDocument(
        session_id=req.session_id,
        role=MessageRole.ASSISTANT,
        content=(
            f"**Approved tests executed:**\n"
            f"  - Passed: {results.get('passed', 0)}\n"
            f"  - Failed: {results.get('failed', 0)}\n"
            f"  - Errors: {results.get('errors', 0)}\n"
            f"  - Duration: {results.get('execution_time_ms', 0) / 1000:.1f}s"
        ),
        message_type=MessageType.TEST_RESULT,
    )
    await messages_col.insert_one(msg.to_mongo())
    await sessions_col.update_one(
        {"_id": ObjectId(req.session_id)},
        {"$set": {"updated_at": _now()}},
    )

    return results


# ============================================
# GET /sessions/{session_id}/tests & /report
# ============================================

@router.get("/sessions/{session_id}/tests", response_model=List[GeneratedTestResponse])
async def get_session_tests(session_id: str):
    _oid(session_id)
    docs = await generated_tests_collection().find(
        {"session_id": session_id}
    ).sort("created_at", 1).to_list(length=200)
    return [GeneratedTestResponse.from_mongo_doc(d) for d in docs]


@router.get("/report/{session_id}")
async def download_report(session_id: str):
    _oid(session_id)
    session = await chat_sessions_collection().find_one(
        {"_id": ObjectId(session_id)}
    )
    report_path = session.get("last_report_path") if session else None

    if not report_path:
        msg = await chat_messages_collection().find_one(
            {"session_id": session_id, "message_type": "report"},
            sort=[("created_at", -1)],
        )
        if msg:
            report_path = (msg.get("metadata") or {}).get("report_path")

    if not report_path or not os.path.exists(report_path):
        raise HTTPException(404, "Report not found. Run tests first.")

    return FileResponse(
        path=report_path,
        filename=os.path.basename(report_path),
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
    )


# ============================================
# WebSocket: /ws/chat/{session_id}
# ============================================

@ws_router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"WS connected: {session_id[:8]}")

    messages_col = chat_messages_collection()
    sessions_col = chat_sessions_collection()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "content": "Invalid JSON"}
                )
                continue

            content = data.get("content", "").strip()
            if not content:
                continue
            if content == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            await websocket.send_json(
                {"type": "ack", "message": "Processing..."}
            )

            user_msg = ChatMessageDocument(
                session_id=session_id,
                role=MessageRole.USER,
                content=content,
            )
            await messages_col.insert_one(user_msg.to_mongo())

            session = await sessions_col.find_one(
                {"_id": ObjectId(session_id)}
            )
            current_state = (
                session.get("state", "idle") if session else "idle"
            )
            target_url = session.get("target_url") if session else None

            settings = get_settings()
            if not settings.groq_configured:
                await websocket.send_json(
                    {"type": "complete", "content": "Groq AI not configured"}
                )
                continue

            content_lower = content.lower().strip()

            # 1. Intercept URL
            if (
                content_lower.startswith("http://")
                or content_lower.startswith("https://")
            ):
                url = content.split()[0]
                await sessions_col.update_one(
                    {"_id": ObjectId(session_id)},
                    {"$set": {"state": SessionState.ANALYZING.value}},
                )
                res = await _process_url_analysis(session_id, url)
                if "error" in res:
                    err_text = res['error'] or 'Unknown browser error'
                    ai_content = f"Cannot access URL: {err_text}"
                else:
                    await sessions_col.update_one(
                        {"_id": ObjectId(session_id)},
                        {"$set": {
                            "target_url": res["final_url"],
                            "state": res["new_state"],
                            "login_required": res["is_login"],
                            "login_completed": False,
                            "browser_session_active": True,
                            "page_analysis": res["page_analysis"],
                            "updated_at": _now(),
                        }},
                    )
                    ai_content = res["msg_content"]

                await websocket.send_json(
                    {"type": "complete", "content": ai_content}
                )
                await messages_col.insert_one(
                    ChatMessageDocument(
                        session_id=session_id,
                        role=MessageRole.ASSISTANT,
                        content=ai_content,
                    ).to_mongo()
                )
                updated = await sessions_col.find_one(
                    {"_id": ObjectId(session_id)}
                )
                await websocket.send_json({
                    "type": "state_update",
                    "state": updated.get("state", "idle"),
                })
                continue

            # 2. Accept Next Page
            if (
                any(w in content_lower for w in [
                    "yes", "sure", "move on", "next", "ok",
                    "do it", "please", "yep", "yeah", "y",
                ])
                and session.get("next_proposed_url")
            ):
                next_url = session.get("next_proposed_url")
                ai_content = await _handle_move_to_next_page(
                    session_id, next_url
                )
                await websocket.send_json(
                    {"type": "complete", "content": ai_content}
                )
                await messages_col.insert_one(
                    ChatMessageDocument(
                        session_id=session_id,
                        role=MessageRole.ASSISTANT,
                        content=ai_content,
                    ).to_mongo()
                )
                updated = await sessions_col.find_one(
                    {"_id": ObjectId(session_id)}
                )
                await websocket.send_json({
                    "type": "state_update",
                    "state": updated.get("state", "idle"),
                })
                continue

            # 3. Handle Login Complete
            if (
                content_lower in {"done", "done.", "i'm done", "im done"}
                and current_state == "waiting_login"
            ):
                ai_content = await _handle_login_complete(
                    session_id, session
                )
                await websocket.send_json(
                    {"type": "complete", "content": ai_content}
                )
                await messages_col.insert_one(
                    ChatMessageDocument(
                        session_id=session_id,
                        role=MessageRole.ASSISTANT,
                        content=ai_content,
                    ).to_mongo()
                )
                updated = await sessions_col.find_one(
                    {"_id": ObjectId(session_id)}
                )
                await websocket.send_json({
                    "type": "state_update",
                    "state": updated.get("state", "idle"),
                })
                continue

            # 4. Decline Next Page
            if (
                any(w in content_lower for w in [
                    "no", "stop", "don't", "dont", "nah", "cancel",
                ])
                and session.get("next_proposed_url")
            ):
                await sessions_col.update_one(
                    {"_id": ObjectId(session_id)},
                    {"$set": {"next_proposed_url": None}},
                )
                ai_content = (
                    "Okay! We will stay on the current page. "
                    "Let me know what you'd like to test next."
                )
                await websocket.send_json(
                    {"type": "complete", "content": ai_content}
                )
                await messages_col.insert_one(
                    ChatMessageDocument(
                        session_id=session_id,
                        role=MessageRole.ASSISTANT,
                        content=ai_content,
                    ).to_mongo()
                )
                continue

            # 5. Standard Chat / Stream
            from app.services.groq_service import groq_service

            intent = groq_service.detect_test_intent(content)
            if (
                intent["is_test_request"]
                and target_url
                and session
                and session.get("browser_session_active")
            ):
                response_text = await _handle_targeted_test(
                    session_id, session, content
                )
                await websocket.send_json(
                    {"type": "complete", "content": response_text}
                )
                await messages_col.insert_one(
                    ChatMessageDocument(
                        session_id=session_id,
                        role=MessageRole.ASSISTANT,
                        content=response_text,
                    ).to_mongo()
                )
                continue

            history_docs = await messages_col.find(
                {"session_id": session_id}
            ).sort("created_at", 1).to_list(length=20)
            history = [
                {
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                }
                for m in history_docs
            ]

            full_response = ""
            try:
                async for token in groq_service.chat_stream(
                    history, session.get("target_url")
                ):
                    full_response += token
                    await websocket.send_json(
                        {"type": "token", "content": token}
                    )
            except Exception as e:
                full_response += f"\nError: {e}"

            await websocket.send_json(
                {"type": "complete", "content": full_response}
            )
            await messages_col.insert_one(
                ChatMessageDocument(
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    content=full_response,
                ).to_mongo()
            )
            await sessions_col.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {"updated_at": _now()}},
            )

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: {session_id[:8]}")
    except Exception as e:
        logger.error(f"WS error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass