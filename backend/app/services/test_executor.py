"""
TestPilot Test Executor - Playwright Version
============================================
Executes AI-generated Playwright Python test code.

Key improvements over Selenium:
- Async-first with auto-waiting
- Network request interception built-in
- Better screenshot capabilities
- More reliable element finding
- Video recording support
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.config import get_settings

logger = logging.getLogger("testpilot.services.test_executor")


class PlaywrightTestExecutor:
    """
    Executes AI-generated Playwright Python test code in a controlled environment.
    """

    def __init__(self, session_id: str, screenshots_dir: Optional[str] = None):
        self.session_id = session_id
        settings = get_settings()
        self.screenshots_dir = screenshots_dir or str(settings.screenshots_dir)
        Path(self.screenshots_dir).mkdir(parents=True, exist_ok=True)
        self.page = None
        self.browser = None
        self.context = None
        self.playwright_instance = None
        self._results: List[Dict[str, Any]] = []

    def _get_or_create_loop(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Loop is closed")
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def _create_browser(self, headless: bool = True):
        loop = self._get_or_create_loop()
        loop.run_until_complete(self._async_create_browser(headless))

    async def _async_create_browser(self, headless: bool = True):
        from playwright.async_api import async_playwright
        self.playwright_instance = await async_playwright().start()
        self.browser = await self.playwright_instance.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--window-size=1920,1080"],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            record_video_dir=None,
        )
        self.page = await self.context.new_page()
        logger.info(f"Playwright browser created for session {self.session_id[:8]}")

    def execute_generated_tests(
        self,
        test_data: Dict[str, Any],
        base_url: str,
        approved_destructive_ids: Optional[Set[str]] = None,
        skip_destructive: bool = True,
        progress_callback=None,
        use_existing_page=None,
    ) -> Dict[str, Any]:
        """Execute all generated test functions."""
        results = {
            "session_id": self.session_id,
            "base_url": base_url,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "pass_rate": 0.0,
            "execution_time_ms": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "test_results": [],
            "destructive_pending": [],
        }

        approved_ids = approved_destructive_ids or set()

        all_tests = []
        for suite in test_data.get("test_suites", []):
            suite_name = suite.get("suite_name", "Default Suite")
            for test in suite.get("tests", []):
                test["_suite_name"] = suite_name
                all_tests.append(test)

        results["total"] = len(all_tests)
        if not all_tests:
            results["finished_at"] = datetime.now(timezone.utc).isoformat()
            return results

        own_browser = False
        if use_existing_page:
            self.page = use_existing_page
            logger.info("Using existing Playwright page")
        else:
            self._create_browser(headless=True)
            own_browser = True

        start_time = time.time()

        try:
            for idx, test in enumerate(all_tests):
                test_id = test.get("test_id", f"TC_{idx + 1:03d}")
                test_name = test.get("test_name", f"Test {idx + 1}")
                is_destructive = test.get("is_destructive", False)

                if progress_callback:
                    try:
                        progress_callback(idx + 1, len(all_tests), test_name, "running")
                    except Exception:
                        pass

                if is_destructive and skip_destructive and test_id not in approved_ids:
                    result = self._create_skipped_result(test, test_id, test_name)
                    results["test_results"].append(result)
                    results["skipped"] += 1
                    results["destructive_pending"].append({
                        "test_id": test_id,
                        "test_name": test_name,
                        "reason": test.get("destructive_reason", "Modifies data"),
                    })
                    continue

                logger.info(f"Executing [{idx + 1}/{len(all_tests)}]: {test_name}")
                test_start = time.time()
                test_result = self._execute_single_test(test, base_url)

                test_result.update({
                    "test_id": test_id,
                    "test_name": test_name,
                    "suite_name": test.get("_suite_name", ""),
                    "description": test.get("description", ""),
                    "category": test.get("category", "functional"),
                    "priority": test.get("priority", "medium"),
                    "is_destructive": is_destructive,
                    "destructive_reason": test.get("destructive_reason"),
                    "expected_result": test.get("expected_result", ""),
                    "playwright_code": test.get("playwright_code", ""),
                    "execution_time_ms": int((time.time() - test_start) * 1000),
                    "tags": test.get("tags", []),
                    "preconditions": test.get("preconditions", []),
                })

                results["test_results"].append(test_result)
                status = test_result.get("status", "error")
                if status == "passed":
                    results["passed"] += 1
                elif status == "failed":
                    results["failed"] += 1
                else:
                    results["errors"] += 1

                logger.info(f"  Result: {status.upper()} ({test_result['execution_time_ms']}ms)")

                if progress_callback:
                    try:
                        progress_callback(idx + 1, len(all_tests), test_name, status)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Test execution batch error: {e}")
            logger.error(traceback.format_exc())
            results["errors"] += 1
        finally:
            if own_browser:
                self.close()

        results["execution_time_ms"] = int((time.time() - start_time) * 1000)
        results["finished_at"] = datetime.now(timezone.utc).isoformat()
        executed = results["passed"] + results["failed"] + results["errors"]
        if executed > 0:
            results["pass_rate"] = round(results["passed"] / executed * 100, 1)

        logger.info(
            f"Execution complete: {results['passed']}/{results['total']} passed, "
            f"{results['pass_rate']}% pass rate"
        )
        return results

    def _execute_single_test(self, test: Dict[str, Any], base_url: str) -> Dict[str, Any]:
        """Execute a single Playwright test."""
        result = {
            "status": "error",
            "actual_result": "",
            "error_message": None,
            "screenshot": None,
            "steps": [],
            "console_logs": [],
        }

        playwright_code = test.get("playwright_code", "") or test.get("selenium_code", "")
        if not playwright_code:
            result["error_message"] = "No test code provided"
            result["actual_result"] = "No test code to execute"
            return result

        playwright_code = self._clean_code(playwright_code)
        test_func_name = self._extract_function_name(playwright_code) or "test_generated"

        if not playwright_code.strip().startswith("def "):
            playwright_code = self._wrap_in_function(playwright_code, test_func_name)

        module_code = self._build_test_module(playwright_code, test_func_name)
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False,
                encoding="utf-8", prefix="testpilot_pw_"
            ) as f:
                f.write(module_code)
                temp_path = f.name

            spec = importlib.util.spec_from_file_location(
                f"testpilot_pw_{int(time.time())}", temp_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            test_func = getattr(module, test_func_name, None)
            if test_func is None:
                for attr_name in dir(module):
                    if attr_name.startswith("test_") and callable(getattr(module, attr_name)):
                        test_func = getattr(module, attr_name)
                        break

            if test_func is None:
                result["error_message"] = f"Function '{test_func_name}' not found"
                result["actual_result"] = "Test function could not be loaded"
                return result

            loop = self._get_or_create_loop()
            test_output = loop.run_until_complete(test_func(self.page, self.screenshots_dir, base_url))

            if isinstance(test_output, dict):
                result["status"] = test_output.get("status", "error")
                result["actual_result"] = test_output.get("actual_result", "")
                result["error_message"] = test_output.get("error_message")
                result["screenshot"] = test_output.get("screenshot")
                result["steps"] = test_output.get("steps", [])
            elif test_output is None:
                result["status"] = "passed"
                result["actual_result"] = "Test completed without errors"
            else:
                result["status"] = "passed"
                result["actual_result"] = str(test_output)

        except SyntaxError as e:
            result["status"] = "error"
            result["error_message"] = f"Syntax error: {e}"
            result["actual_result"] = f"Syntax error on line {e.lineno}: {e.msg}"
            self._safe_screenshot(result, test.get("test_id", "syntax_error"))
        except Exception as e:
            result["status"] = "error"
            result["error_message"] = f"Execution error: {str(e)}"
            result["actual_result"] = f"Error: {str(e)}"
            result["steps"].append({
                "step": 0, "action": "Test execution",
                "status": "error", "error": traceback.format_exc()[-500:]
            })
            self._safe_screenshot(result, test.get("test_id", "exec_error"))
            logger.error(f"Test execution error: {e}")
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        return result

    def _build_test_module(self, playwright_code: str, func_name: str) -> str:
        return f'''# Auto-generated Playwright test module by TestPilot
# Session: {self.session_id[:8]}

import os
import sys
import asyncio
import traceback
import time


async def {func_name}(page, screenshots_dir, base_url):
    """Test function wrapper."""
    pass


{playwright_code}
'''

    def _clean_code(self, code: str) -> str:
        if not code:
            return code
        code = code.strip()
        for prefix in ("```python", "```"):
            if code.startswith(prefix):
                code = code[len(prefix):]
                break
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()
        code = code.replace("\\n", "\n").replace("\\t", "\t")
        code = code.replace('\\"', '"').replace("\\'", "'")
        return code

    def _extract_function_name(self, code: str) -> Optional[str]:
        import re
        match = re.search(r"(?:async\s+)?def\s+(test_\w+)\s*\(", code)
        if match:
            return match.group(1)
        match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", code)
        if match:
            return match.group(1)
        return None

    def _wrap_in_function(self, code: str, func_name: str) -> str:
        lines = code.split("\n")
        indented = "\n".join(f"    {line}" for line in lines)
        return f'''async def {func_name}(page, screenshots_dir, base_url):
    """Auto-wrapped test function."""
    result = {{
        "status": "passed", "actual_result": "", 
        "error_message": None, "screenshot": None, "steps": []
    }}
    try:
{indented}
        result["actual_result"] = "Test completed successfully"
    except AssertionError as ae:
        result["status"] = "failed"
        result["error_message"] = str(ae)
        result["actual_result"] = f"Assertion failed: {{str(ae)}}"
    except Exception as e:
        result["status"] = "failed"
        result["error_message"] = str(e)
        result["actual_result"] = f"Error: {{str(e)}}"
    return result
'''

    def _create_skipped_result(self, test, test_id, test_name):
        return {
            "test_id": test_id, "test_name": test_name,
            "suite_name": test.get("_suite_name", ""),
            "description": test.get("description", ""),
            "category": test.get("category", "functional"),
            "priority": test.get("priority", "medium"),
            "is_destructive": True,
            "destructive_reason": test.get("destructive_reason", "Modifies data"),
            "status": "skipped",
            "actual_result": "Skipped: Requires approval (destructive action)",
            "expected_result": test.get("expected_result", ""),
            "error_message": "Requires user approval",
            "screenshot": None, "steps": [], "execution_time_ms": 0,
            "playwright_code": test.get("playwright_code", ""),
            "tags": test.get("tags", []), "preconditions": test.get("preconditions", []),
            "console_logs": [],
        }

    def _safe_screenshot(self, result: Dict, test_id: str):
        try:
            if self.page and not self.page.is_closed():
                loop = self._get_or_create_loop()
                ts = int(time.time())
                sid = self.session_id[:8]
                clean_id = "".join(c for c in str(test_id) if c.isalnum() or c in "_-")
                fname = f"{sid}_{clean_id}_error_{ts}.png"
                fpath = os.path.join(self.screenshots_dir, fname)
                loop.run_until_complete(self.page.screenshot(path=fpath, full_page=True))
                result["screenshot"] = fpath
        except Exception as e:
            logger.debug(f"Could not save screenshot: {e}")

    def close(self):
        if self.playwright_instance:
            loop = self._get_or_create_loop()
            try:
                loop.run_until_complete(self._async_close())
            except Exception as e:
                logger.debug(f"Close error: {e}")

    async def _async_close(self):
        if self.page and not self.page.is_closed():
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright_instance:
            await self.playwright_instance.stop()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright_instance = None
        logger.info(f"Browser closed for session {self.session_id[:8]}")


def execute_tests_for_session(
    session_id: str,
    test_data: Dict[str, Any],
    base_url: str,
    approved_destructive_ids: Optional[Set[str]] = None,
    skip_destructive: bool = True,
    progress_callback=None,
    existing_driver=None,
) -> Dict[str, Any]:
    """Convenience function - Playwright version."""
    executor = PlaywrightTestExecutor(session_id)
    try:
        return executor.execute_generated_tests(
            test_data=test_data,
            base_url=base_url,
            approved_destructive_ids=approved_destructive_ids,
            skip_destructive=skip_destructive,
            progress_callback=progress_callback,
            use_existing_page=existing_driver,
        )
    finally:
        if not existing_driver:
            executor.close()