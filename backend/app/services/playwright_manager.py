"""
TestPilot Playwright Browser Session Manager
============================================
Replaces Selenium with Playwright for:
- Faster, more reliable automation
- Built-in network interception
- Better async support
- Auto-waiting for elements
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.config import get_settings

logger = logging.getLogger("testpilot.services.playwright_manager")


# ── Constants ──────────────────────────────────────────────────────────────

BROWSER_IDLE_TIMEOUT = 900  # seconds — overridden by settings at runtime


# ── Per-session state ──────────────────────────────────────────────────────

class PlaywrightSession:
    """Wraps a Playwright browser context with session metadata."""

    def __init__(self, session_id: str):
        self.session_id       = session_id
        self.browser          = None
        self.context          = None
        self.page             = None
        self.playwright       = None

        self.created_at       = time.time()
        self.last_used_at     = time.time()

        self.current_url:     Optional[str]           = None
        self.is_logged_in:    bool                    = False
        self.login_required:  bool                    = False
        self.page_html:       Optional[str]           = None
        self.page_title:      Optional[str]           = None
        self.crawled_pages:   List[Dict[str, str]]    = []
        self.network_requests: List[Dict[str, Any]]   = []
        self.headless:        Optional[bool]          = None

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()

    # ── Helpers ────────────────────────────────────────────────────────

    def touch(self) -> None:
        self.last_used_at = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used_at

    @property
    def is_expired(self) -> bool:
        timeout = getattr(get_settings(), "BROWSER_IDLE_TIMEOUT", BROWSER_IDLE_TIMEOUT)
        return self.idle_seconds > timeout

    @property
    def is_running(self) -> bool:
        return (
            self.page is not None
            and self._loop is not None
            and self._thread is not None
            and self._thread.is_alive()
        )

    # Shim so callers that reference .driver can re-use the active page
    @property
    def driver(self):
        return self.page

    def _start_event_loop(self) -> None:
        if sys.platform == "win32":
            policy = asyncio.WindowsProactorEventLoopPolicy()
            self._loop = policy.new_event_loop()
        else:
            self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    def _ensure_event_loop(self) -> None:
        if self._thread and self._thread.is_alive() and self._loop is not None:
            return
        self._loop_ready.clear()
        self._thread = threading.Thread(
            target=self._start_event_loop,
            daemon=True,
        )
        self._thread.start()
        if not self._loop_ready.wait(timeout=15):
            raise RuntimeError("Failed to start Playwright session event loop")
        if self._loop is None:
            raise RuntimeError("Playwright session event loop not available")

    def _run_coroutine(self, coro: asyncio.coroutine) -> Any:
        self._ensure_event_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start_browser(self, headless: bool = False) -> None:
        """Launch Playwright browser synchronously."""
        if self.is_running:
            return
        self._ensure_event_loop()
        self._run_coroutine(self._async_start(headless))
        logger.info(
            f"[{self.session_id[:8]}] Browser started (headless={headless})"
        )

    async def _async_start(self, headless: bool = False) -> None:
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        try:
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-infobars",
                    "--disable-notifications",
                    "--window-size=1920,1080",
                ],
            )
            self.headless = headless
        except Exception as e:
            logger.warning(
                f"[{self.session_id[:8]}] Browser launch failed (headless={headless}): {e}"
            )
            if not headless:
                logger.info(
                    f"[{self.session_id[:8]}] Retrying browser launch in headless mode"
                )
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-infobars",
                        "--disable-notifications",
                        "--window-size=1920,1080",
                    ],
                )
                self.headless = True
            else:
                raise

        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        await self.context.route("**/*", self._handle_route)
        self.page = await self.context.new_page()
        self.page.on(
            "console",
            lambda msg: logger.debug(f"[{self.session_id[:8]}] console: {msg.text}"),
        )

    async def _handle_route(self, route, request) -> None:
        """Intercept and log API network requests."""
        try:
            if (
                request.method in ("POST", "PUT", "DELETE", "PATCH")
                or any(kw in request.url for kw in ("api", "graphql", "json"))
            ):
                self.network_requests.append({
                    "method":        request.method,
                    "url":           request.url,
                    "resource_type": request.resource_type,
                })
        except Exception:
            pass
        await route.continue_()

    def close(self) -> None:
        """Shut down browser and Playwright."""
        if self._loop is None or self._thread is None:
            self.headless = None
            logger.info(f"[{self.session_id[:8]}] Browser closed")
            return

        try:
            self._run_coroutine(self._async_close())
        except Exception as e:
            logger.debug(f"[{self.session_id[:8]}] Close error: {e}")

        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)
        except Exception as e:
            logger.debug(f"[{self.session_id[:8]}] Close thread error: {e}")

        self._thread = None
        self._loop = None
        self._loop_ready.clear()
        self.headless = None
        logger.info(f"[{self.session_id[:8]}] Browser closed")

    async def _async_close(self) -> None:
        if self.page and not self.page.is_closed():
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.page      = None
        self.context   = None
        self.browser   = None
        self.playwright = None

    # ── Navigation ─────────────────────────────────────────────────────

    def navigate(self, url: str, wait_seconds: float = 2.5) -> str:
        """Navigate to URL and return page HTML."""
        if not self.is_running:
            self.start_browser(headless=False)
        self.touch()
        return self._run_coroutine(self._async_navigate(url, wait_seconds))

    async def _async_navigate(self, url: str, wait_seconds: float) -> str:
        logger.info(f"[{self.session_id[:8]}] Navigating → {url}")
        settings = get_settings()
        timeout = settings.PAGE_LOAD_TIMEOUT
        await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if wait_seconds > 0:
            await self.page.wait_for_timeout(int(wait_seconds * 1000))
        try:
            await self.page.wait_for_load_state(
                "networkidle",
                timeout=min(10_000, timeout),
            )
        except Exception:
            pass
        self.current_url = self.page.url
        self.page_html   = await self.page.content()
        self.page_title  = await self.page.title()
        logger.info(
            f"[{self.session_id[:8]}] Loaded: {self.page_title!r} "
            f"({len(self.page_html):,} chars)"
        )
        return self.page_html

    # ── Page data ──────────────────────────────────────────────────────

    def get_current_html(self) -> str:
        if not self.is_running:
            return self.page_html or ""
        try:
            html = self._run_coroutine(self.page.content())
            self.page_html   = html
            self.current_url = self.page.url
            self.page_title  = self._run_coroutine(self.page.title())
            return html
        except Exception as e:
            logger.warning(f"[{self.session_id[:8]}] get_current_html: {e}")
            return self.page_html or ""

    def get_current_state(self) -> Dict[str, Any]:
        if not self.is_running:
            return {
                "url": self.current_url or "",
                "title": self.page_title or "",
                "html_length": 0,
                "is_running": False,
            }
        try:
            title = self._run_coroutine(self.page.title())
            html = self._run_coroutine(self.page.content())
            return {
                "url":         self.page.url,
                "title":       title,
                "html_length": len(html),
                "is_running":  True,
            }
        except Exception:
            return {
                "url": self.current_url or "",
                "title": self.page_title or "",
                "html_length": 0,
                "is_running": False,
            }

    def get_page_apis(self) -> List[str]:
        """Return captured API calls then clear the buffer."""
        apis = list(dict.fromkeys(
            f"{r['method']} {r['url']}" for r in self.network_requests
        ))
        self.network_requests.clear()
        return apis

    def get_navigable_links(self) -> List[str]:
        if not self.is_running:
            return []
        return self._run_coroutine(self._async_get_links())

    async def _async_get_links(self) -> List[str]:
        links: List[str] = []
        try:
            base_domain = urlparse(self.page.url).netloc
            hrefs: List[str] = await self.page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)"
            )
            current_clean = self.page.url.split("#")[0].rstrip("/")
            for href in hrefs:
                if not href:
                    continue
                parsed = urlparse(href)
                if parsed.netloc and parsed.netloc != base_domain:
                    continue
                if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                    continue
                if any(href.endswith(ext) for ext in
                       (".pdf", ".jpg", ".png", ".zip", ".csv", ".xml")):
                    continue
                clean = href.split("#")[0].rstrip("/")
                if clean and clean != current_clean and clean not in links:
                    links.append(clean)
        except Exception as e:
            logger.warning(f"[{self.session_id[:8]}] Link extraction: {e}")
        return links[:20]

    def get_page_interactive_elements(self) -> Dict[str, Any]:
        if not self.is_running:
            return {}
        return self._run_coroutine(self._async_get_elements())

    async def _async_get_elements(self) -> Dict[str, Any]:
        try:
            buttons = await self.page.eval_on_selector_all(
                "button, input[type='submit'], input[type='button'], [role='button']",
                """els => els.slice(0, 30).map(e => ({
                    text: (e.textContent || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 60),
                    tag:  e.tagName.toLowerCase(),
                    type: e.type || '',
                    id:   e.id || '',
                })).filter(b => b.text)""",
            )
            forms = await self.page.eval_on_selector_all(
                "form",
                """forms => forms.slice(0, 10).map(f => ({
                    action: f.action || '',
                    method: f.method || 'GET',
                    fields: Array.from(f.querySelectorAll('input,select,textarea'))
                        .filter(i => !['hidden','submit','button'].includes(i.type))
                        .slice(0, 10)
                        .map(i => ({ name: i.name || i.id || '', type: i.type || 'text' }))
                })).filter(f => f.fields.length > 0)""",
            )
            links = await self.page.eval_on_selector_all(
                "a",
                """els => els.slice(0, 30)
                    .filter(a => a.textContent.trim() && a.href)
                    .map(a => ({ text: a.textContent.trim().slice(0, 40), href: a.href }))""",
            )
            return {
                "buttons":       buttons,
                "forms":         forms,
                "links":         links,
                "total_buttons": len(buttons),
                "total_forms":   len(forms),
                "total_links":   len(links),
            }
        except Exception as e:
            logger.warning(f"[{self.session_id[:8]}] Element scan: {e}")
            return {}

    # ── Screenshot ─────────────────────────────────────────────────────

    def take_screenshot(self, name: str) -> Optional[str]:
        if not self.is_running:
            return None
        return self._run_coroutine(self._async_screenshot(name))

    async def _async_screenshot(self, name: str) -> Optional[str]:
        try:
            screenshots_dir = Path(get_settings().screenshots_dir)
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            clean = "".join(c for c in name if c.isalnum() or c in "_-")
            fname = f"{self.session_id[:8]}_{clean}_{int(time.time())}.png"
            fpath = str(screenshots_dir / fname)
            await self.page.screenshot(path=fpath, full_page=True)
            self.touch()
            logger.debug(f"[{self.session_id[:8]}] Screenshot → {fpath}")
            return fpath
        except Exception as e:
            logger.warning(f"[{self.session_id[:8]}] Screenshot failed: {e}")
            return None

    def get_console_logs(self) -> List[str]:
        return []


# ── Session manager (singleton) ────────────────────────────────────────────

class PlaywrightSessionManager:
    """Thread-safe pool of PlaywrightSession objects."""

    def __init__(self) -> None:
        self._sessions: Dict[str, PlaywrightSession] = {}
        self._lock             = threading.Lock()
        self._cleanup_task: Optional[asyncio.Task]   = None

    # ── Public API ─────────────────────────────────────────────────────

    def get_or_create(
        self,
        session_id: str,
        headless: Optional[bool] = None,
        force_restart: bool = False,
    ) -> PlaywrightSession:
        if headless is None:
            headless = get_settings().PLAYWRIGHT_HEADLESS

        with self._lock:
            ps = self._sessions.get(session_id)
            if ps:
                if force_restart:
                    try:
                        ps.close()
                    except Exception:
                        pass
                    ps = None
                elif ps.is_running and ps.headless == headless:
                    ps.touch()
                    return ps
                elif ps.is_running and ps.headless != headless:
                    try:
                        ps.close()
                    except Exception:
                        pass
                    ps = None
                elif not ps.is_running:
                    try:
                        ps.close()
                    except Exception:
                        pass
                    ps = None

            if not ps:
                ps = PlaywrightSession(session_id)
                ps.start_browser(headless=headless)
                self._sessions[session_id] = ps
                logger.info(f"Created Playwright session {session_id[:8]}")
            return ps

    def get(self, session_id: str) -> Optional[PlaywrightSession]:
        with self._lock:
            ps = self._sessions.get(session_id)
            if ps:
                ps.touch()
            return ps

    def close_session(self, session_id: str) -> None:
        with self._lock:
            ps = self._sessions.pop(session_id, None)
        if ps:
            try:
                ps.close()
            except Exception:
                pass
            logger.info(f"Closed session {session_id[:8]}")

    def close_all(self) -> None:
        with self._lock:
            ids = list(self._sessions.keys())
        for sid in ids:
            self.close_session(sid)

    def cleanup_expired(self) -> None:
        with self._lock:
            expired = [
                sid for sid, ps in self._sessions.items() if ps.is_expired
            ]
        for sid in expired:
            logger.info(f"Reaping idle session {sid[:8]}")
            self.close_session(sid)

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for ps in self._sessions.values() if ps.is_running)

    # ── Cleanup loop ───────────────────────────────────────────────────

    async def start_cleanup_loop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Playwright cleanup loop started")

    async def stop_cleanup_loop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self.close_all()
        logger.info("Playwright cleanup loop stopped")

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                await asyncio.to_thread(self.cleanup_expired)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(30)


# ── Module-level singletons ────────────────────────────────────────────────
# Import either name — both refer to the same object.

playwright_manager = PlaywrightSessionManager()
browser_manager    = playwright_manager          # backward-compat alias