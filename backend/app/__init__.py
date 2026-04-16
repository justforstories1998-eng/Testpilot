"""
TestPilot Backend Application
==============================
Universal Automated Website Testing Platform.

This package contains the complete backend:

    app/
    ├── main.py          — FastAPI application entry point
    ├── config.py        — Settings & environment configuration
    ├── database.py      — MongoDB Atlas async connection (Motor)
    ├── models/          — MongoDB document schemas (Pydantic)
    │   ├── project.py   — Project configuration documents
    │   ├── test_run.py  — Test run & result documents
    │   └── user.py      — User authentication (optional)
    ├── schemas/         — API request/response schemas (Pydantic)
    │   ├── test_run.py  — Test execution API shapes
    │   ├── project.py   — Project API shapes
    │   └── report.py    — Report & comparison API shapes
    ├── api/             — FastAPI route modules
    │   ├── routes/      — REST API endpoints
    │   └── websocket.py — Socket.IO real-time events
    ├── services/        — Business logic & test engines
    │   ├── test_executor.py       — Main orchestrator
    │   ├── browser_manager.py     — Selenium Chrome management
    │   ├── crawler.py             — Page discovery engine
    │   ├── page_analyzer.py       — Element detection
    │   ├── button_tester.py       — Button interaction tests
    │   ├── form_tester.py         — Form validation tests
    │   ├── api_tester.py          — API endpoint tests
    │   ├── accessibility_tester.py — WCAG compliance checks
    │   ├── performance_tester.py  — Page load metrics
    │   ├── auth_handler.py        — Login automation
    │   ├── screenshot_service.py  — Screenshot capture
    │   ├── video_recorder.py      — Browser window recording
    │   ├── step_tracker.py        — Steps to reproduce
    │   ├── failure_analyzer.py    — Root cause analysis
    │   ├── report_generator.py    — Excel + HTML reports
    │   └── test_case_parser.py    — Uploaded file parsing
    └── utils/           — Shared utilities
        ├── html_parser.py         — HTML element extraction
        ├── element_classifier.py  — UI element classification
        └── safe_actions.py        — Dangerous action filtering

Quick Start:
    # Start FastAPI server
    cd backend
    uvicorn app.main:asgi_app --reload --host 0.0.0.0 --port 8000

    # Start Celery worker (in separate terminal)
    cd backend
    celery -A celery_app worker --loglevel=info --pool=solo

Architecture:
    - FastAPI handles HTTP requests and WebSocket connections
    - Celery workers handle background test execution
    - MongoDB Atlas stores all data (projects, runs, results)
    - Redis serves as Celery broker and WebSocket event bus
    - Selenium automates Chrome browser for testing
    - Socket.IO provides real-time progress updates

No Docker required. Everything runs directly on the local machine.
"""

__version__ = "1.0.0"
__app_name__ = "TestPilot"