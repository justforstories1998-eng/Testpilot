"""
TestPilot Groq AI Service
================================================================
Generates comprehensive, executable Selenium tests that:
- Fixes URL duplication issues (strict base_url rules)
- Outputs Azure DevOps TSV format automatically
"""

from __future__ import annotations

import json
import re
import time
import logging
from typing import AsyncGenerator, Optional, List, Dict, Any

from app.config import get_settings

logger = logging.getLogger("testpilot.services.groq")


# Playwright prompt used for generating Selenium-compatible test suites:

SYSTEM_PROMPT_GENERATE_SELENIUM = """You are TestPilot AI, a world-class QA automation engineer. Generate COMPREHENSIVE, EXECUTABLE Playwright Python async test code AND a structured manual test plan.

CRITICAL RULES:
1. Every test function MUST BE: async def test_xxx(page, screenshots_dir, base_url)
2. CRITICAL URL RULE: Use ONLY `await page.goto(base_url)`. NEVER append paths.
3. Use Playwright's built-in auto-waiting - NO time.sleep()
4. Every function must return a result dict with status, actual_result, error_message, screenshot, steps
5. Use REAL CSS selectors from the provided HTML
6. Generate exactly 5 comprehensive tests for this specific page
7. Use `await page.wait_for_selector()` for element waiting
8. Use `await page.screenshot(path=screenshot_path)` for screenshots
9. Use `await page.locator()` for reliable element finding

PLAYWRIGHT PATTERNS TO USE:
- Navigation: await page.goto(base_url)
- Click: await page.locator('selector').click()
- Fill: await page.locator('selector').fill('value')
- Wait: await page.wait_for_selector('selector', timeout=10000)
- Assert visible: await page.locator('selector').is_visible()
- Get text: await page.locator('selector').text_content()
- Screenshot: await page.screenshot(path=screenshot_path, full_page=True)
- Network wait: await page.wait_for_load_state('networkidle')
- Evaluate: await page.evaluate('() => document.title')

TEST SCENARIO CATEGORIES (generate at least one of each):
1. Page Load & Navigation - verify page loads, title correct, key elements present
2. Form Validation - test required fields, invalid data, successful submission
3. Interactive Elements - buttons, dropdowns, modals, toggles
4. Data Display - tables, lists, search results correctness
5. Error Handling - 404 pages, empty states, error messages

TSV EXCEL TEST PLAN GENERATION:
Generate Tab-Separated Values matching Azure DevOps format.
Columns: ID\\tWork Item Type\\tTitle\\tTest Step\\tStep Action\\tStep Expected\\tArea Path\\tAssigned To\\tState\\tScenario Type

OUTPUT FORMAT (JSON only):
{
  "ado_test_plan": "...",
  "test_suites": [
    {
      "suite_name": "Suite Name",
      "tests": [
        {
          "test_id": "TC_001",
          "test_name": "Descriptive Test Name",
          "description": "What this test verifies",
          "category": "functional|ui|security|performance|accessibility",
          "priority": "critical|high|medium|low",
          "is_destructive": false,
          "preconditions": ["User is on the page", "Browser is fresh"],
          "steps": [
            {"step": 1, "action": "Navigate to page", "expected": "Page loads successfully"},
            {"step": 2, "action": "Check title", "expected": "Title is correct"}
          ],
          "playwright_code": "async def test_xxx(page, screenshots_dir, base_url):\\n    result = {...}\\n    try:\\n        await page.goto(base_url)\\n        ...\\n    except Exception as e:\\n        result['status'] = 'failed'\\n        result['error_message'] = str(e)\\n    return result",
          "expected_result": "Clear description of expected outcome",
          "tags": ["smoke", "regression"],
          "destructive_reason": null
        }
      ]
    }
  ]
}

RETURN ONLY VALID JSON. Properly escape all strings."""


SYSTEM_PROMPT_TARGETED_TEST = """You are TestPilot AI. Generate a SINGLE focused Selenium test based on the user's specific instruction.
Return ONLY this JSON:
{
  "test_name": "Descriptive name",
  "description": "What this test does",
  "category": "functional",
  "priority": "high",
  "is_destructive": false,
  "selenium_code": "def test_custom(driver, screenshots_dir, base_url):\\n    ...",
  "expected_result": "What should happen"
}"""

SYSTEM_PROMPT_CHAT = """You are TestPilot AI, an expert QA engineer assistant.
Help users understand test results. Be concise and professional."""

SYSTEM_PROMPT_LOGIN_DETECT = """You are an AI assistant that detects whether the provided web page requires user login.
Return ONLY valid JSON with the following fields:
{
  "is_login_page": true|false,
  "confidence": 0.0,
  "page_type": "login|dashboard|form|unknown",
  "page_title": "string"
}
Use the provided HTML and URL to decide. Do not include any extra text outside the JSON."""

SYSTEM_PROMPT_PAGE_ANALYSIS = """You are an AI page analyst. Analyze the provided URL and page HTML.
Return ONLY valid JSON with these fields:
{
  "page_type": "dashboard|form|product|listing|unknown",
  "page_title": "string",
  "page_description": "string",
  "key_features": [],
  "has_crud_operations": true|false,
  "crud_details": {"can_create": true|false, "can_read": true|false, "can_update": true|false, "can_delete": true|false},
  "technologies_detected": [],
  "potential_test_areas": [],
  "accessibility_notes": []
}
Do not include any explanation or conversation text."""

SYSTEM_PROMPT_FAILURE = """You are an expert QA failure analyst. Analyze the failure clearly.
Return ONLY this JSON:
{
  "root_cause": "Simple explanation",
  "technical_details": "Technical explanation",
  "category": "bug|environment|selector_changed|timeout",
  "suggested_fix": "How to fix"
}"""


_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqService:
    def __init__(self):
        self._sync_client = None
        self._async_client = None

    def _ensure_sync_client(self):
        if self._sync_client is not None:
            return
        settings = get_settings()
        if not settings.groq_configured:
            raise RuntimeError("Groq AI not configured. Set GROQ_API_KEY in .env")
        from openai import OpenAI
        self._sync_client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=_GROQ_BASE_URL,
        )

    def _ensure_async_client(self):
        if self._async_client is not None:
            return
        settings = get_settings()
        if not settings.groq_configured:
            raise RuntimeError("Groq AI not configured.")
        from openai import AsyncOpenAI
        self._async_client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=_GROQ_BASE_URL,
        )

    @property
    def model(self) -> str:
        return get_settings().GROQ_MODEL

    @property
    def is_configured(self) -> bool:
        return get_settings().groq_configured

    def detect_login_page(self, html_content: str, url: str) -> Dict[str, Any]:
        self._ensure_sync_client()
        html_trimmed = self._trim_html(html_content, 12000)

        try:
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_LOGIN_DETECT},
                    {"role": "user", "content": f"URL: {url}\n\nHTML:\n```html\n{html_trimmed}\n```"},
                ],
                temperature=0.05,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Login detection error: {e}")
            return {"is_login_page": False, "confidence": 0, "page_type": "unknown", "page_title": "", "reasoning": str(e)}

    def analyze_page(self, html_content: str, url: str) -> Dict[str, Any]:
        self._ensure_sync_client()
        html_trimmed = self._trim_html(html_content, 12000)

        try:
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_PAGE_ANALYSIS},
                    {"role": "user", "content": f"URL: {url}\n\nHTML:\n```html\n{html_trimmed}\n```"},
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Page analysis error: {e}")
            return {"page_type": "unknown", "key_features": [], "has_crud_operations": False, "interactive_elements": {}}

    def generate_selenium_tests(
        self,
        url: str,
        html_content: str,
        page_analysis: Optional[Dict[str, Any]] = None,
        additional_instructions: Optional[str] = None,
        interactive_elements: Optional[Dict[str, Any]] = None,
        apis: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        self._ensure_sync_client()
        settings = get_settings()
        
        user_prompt = f"Generate Selenium tests specifically for this exact page.\n\n"
        user_prompt += f"URL: {url}\n\n"

        if apis:
            user_prompt += f"**Detected APIs / Network Calls ({len(apis)}):**\n"
            for api in apis[:15]:
                user_prompt += f"  - {api}\n"
            user_prompt += "Include tests that verify these specific API endpoints if relevant.\n\n"

        if interactive_elements:
            buttons = interactive_elements.get("buttons", [])
            forms = interactive_elements.get("forms", [])
            if buttons:
                user_prompt += f"**Buttons:**\n"
                for btn in buttons[:20]:
                    user_prompt += f"  - \"{btn['text']}\" (id: {btn.get('id','')}, class: {btn.get('classes','')[:30]})\n"
            if forms:
                user_prompt += f"**Forms:**\n"
                for form in forms[:5]:
                    user_prompt += f"  - Action: {form.get('action','N/A')} Method: {form.get('method','GET')}\n"
            user_prompt += "\n"

        if page_analysis:
            user_prompt += f"**Analysis:** Type: {page_analysis.get('page_type', 'unknown')}\n"
            crud = page_analysis.get("crud_details", {})
            if crud:
                user_prompt += f"CRUD: {crud}\n"
            user_prompt += "\n"

        # Truncate to 6000 chars to avoid hitting token limits
        html_trimmed = self._trim_html(html_content, 6000)
        user_prompt += f"**Page HTML:**\n```html\n{html_trimmed}\n```\n\n"
        
        if additional_instructions:
            user_prompt += f"**User Instructions:** {additional_instructions}\n\n"

        user_prompt += f"Generate exactly 5 thorough tests focused on this page."
        
        for attempt in range(3):
            try:
                response = self._sync_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_GENERATE_SELENIUM},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=settings.GROQ_TEMPERATURE,
                    max_tokens=settings.GROQ_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                
                content = response.choices[0].message.content
                
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    cleaned = self._extract_json(content)
                    if cleaned:
                        result = json.loads(cleaned)
                    else:
                        raise ValueError("Invalid JSON string returned")

                if "test_suites" in result:
                    return result
                return {}
                
            except Exception as e:
                err_str = str(e).lower()
                logger.warning(f"Generation attempt {attempt + 1} failed: {e}")
                if "429" in err_str or "rate limit" in err_str or "too many" in err_str:
                    logger.info("Groq Rate Limit hit. Waiting 20 seconds before retry...")
                    time.sleep(20)  
                else:
                    time.sleep(5)
                    
        return {}

    def generate_targeted_test(
        self, user_instruction: str, html_content: str, url: str, interactive_elements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._ensure_sync_client()
        html_trimmed = self._trim_html(html_content, 8000)
        context = f"User instruction: {user_instruction}\n\nURL: {url}\n\n"

        if interactive_elements:
            buttons = interactive_elements.get("buttons", [])
            if buttons:
                context += "Available buttons:\n"
                for btn in buttons[:15]:
                    context += f"  - \"{btn['text']}\" (id: {btn.get('id', '')}, class: {btn.get('classes', '')[:40]})\n"
                context += "\n"

        context += f"HTML:\n```html\n{html_trimmed}\n```"

        try:
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_TARGETED_TEST},
                    {"role": "user", "content": context},
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Targeted test generation error: {e}")
            raise

    def detect_test_intent(self, message: str) -> Dict[str, Any]:
        msg_lower = message.lower().strip()
        test_patterns = ["test ", "click ", "check ", "verify ", "validate ", "fill ", "submit ", "try ", "press ", "open ", "navigate to ", "go to ", "search for ", "type ", "enter ", "select ", "scroll ", "hover ", "test the ", "click the ", "check the ", "verify the ", "can you test", "please test", "run a test", "test if ", "check if ", "see if "]
        is_test_request = any(msg_lower.startswith(p) or f" {p}" in msg_lower for p in test_patterns)
        run_patterns = ["run the tests", "execute tests", "start testing", "run tests", "execute the tests"]
        is_run_request = any(p in msg_lower for p in run_patterns)
        gen_patterns = ["generate tests", "create tests", "make tests", "build tests"]
        is_gen_request = any(p in msg_lower for p in gen_patterns)

        return {
            "is_test_request": is_test_request,
            "is_run_request": is_run_request,
            "is_generate_request": is_gen_request,
            "instruction": message,
        }

    def chat(self, messages: List[Dict[str, str]], target_url: Optional[str] = None) -> str:
        self._ensure_sync_client()
        system_content = SYSTEM_PROMPT_CHAT
        if target_url:
            system_content += f"\n\nCurrent testing context: {target_url}"

        formatted = [{"role": "system", "content": system_content}]
        for msg in messages[-20:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                formatted.append({"role": role, "content": content})

        try:
            response = self._sync_client.chat.completions.create(
                model=self.model, messages=formatted, temperature=0.3, max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise

    async def chat_stream(self, messages: List[Dict[str, str]], target_url: Optional[str] = None) -> AsyncGenerator[str, None]:
        self._ensure_async_client()
        system_content = SYSTEM_PROMPT_CHAT
        if target_url:
            system_content += f"\n\nTesting context: {target_url}"

        formatted = [{"role": "system", "content": system_content}]
        for msg in messages[-20:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                formatted.append({"role": role, "content": content})

        try:
            stream = await self._async_client.chat.completions.create(
                model=self.model, messages=formatted, temperature=0.3, max_tokens=4096, stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"\n\nError: {str(e)}"

    def analyze_failure(self, test_name: str, test_description: str, selenium_code: str,
                        error_message: str, steps_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._ensure_sync_client()
        user_prompt = (
            f"Test: {test_name}\nDescription: {test_description}\n"
            f"Error: {error_message}\n\nCode:\n```python\n{selenium_code[:3000]}\n```\n\n"
            f"Steps: {json.dumps(steps_results[:20], default=str)[:2000]}"
        )

        try:
            response = self._sync_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_FAILURE},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1, max_tokens=4096,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {
                "root_cause": f"Test '{test_name}' failed: {error_message[:200]}",
                "technical_details": error_message,
                "category": "unknown", "severity": "medium",
                "suggested_fix": "Check selectors and page structure",
                "regression_risk": "medium",
            }

    def _trim_html(self, html: str, max_chars: int = 12000) -> str:
        if not html:
            return ""
        if len(html) <= max_chars:
            return html

        html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<!--[\s\S]*?-->', '', html)
        html = re.sub(r'<svg[^>]*>[\s\S]*?</svg>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'\s+', ' ', html)
        html = re.sub(r'\s+data-[a-zA-Z0-9-]+="[^"]*"', '', html)

        if len(html) <= max_chars:
            return html
        return html[:max_chars] + "\n<!-- truncated -->"

    def _extract_json(self, text: str) -> Optional[str]:
        if not text:
            return None
        for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```", r"(\{[\s\S]*\})"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                candidate = match.group(1).strip()
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue
        return None

groq_service = GroqService()