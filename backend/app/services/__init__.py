"""
TestPilot Services Package
===========================
Business logic and test execution engines.

Services are the core of TestPilot — they contain all the
logic for crawling websites, analyzing pages, testing elements,
recording evidence, and generating reports.

Service Architecture:
    
    TestExecutor (orchestrator)
    ├── BrowserManager        — Creates/manages Chrome instances
    ├── AuthHandler           — Handles website login
    ├── Crawler               — Discovers pages via navigation
    ├── PageAnalyzer          — Identifies testable elements
    │   └── HTMLParser        — Parses pasted HTML offline
    ├── ButtonTester          — Tests button interactions
    ├── FormTester            — Tests form validation
    ├── ApiTester             — Tests API endpoints
    ├── AccessibilityTester   — WCAG compliance checks
    ├── PerformanceTester     — Page load metrics
    ├── ScreenshotService     — Captures screenshots
    ├── VideoRecorder         — Records browser window
    ├── StepTracker           — Records steps to reproduce
    ├── FailureAnalyzer       — Analyzes test failures
    ├── ReportGenerator       — Creates Excel + HTML reports
    └── TestCaseParser        — Parses uploaded test files

Communication:
    Services running in Celery workers communicate progress
    to the frontend via:
    
    Service → emit_log/emit_progress → Redis pub/sub →
    WebSocketBridge → Socket.IO → Frontend

Data Flow:
    1. User starts test → FastAPI creates TestRun in MongoDB
    2. Celery picks up task → TestExecutor runs
    3. Each test result → inserted into MongoDB as TestResultDocument
    4. Progress updates → sent via Redis → Socket.IO
    5. Completion → reports generated → paths saved in MongoDB
    6. Frontend polls/receives results → renders report
"""