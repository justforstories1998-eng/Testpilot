/* =================================================================
   TESTPILOT — TYPE SYSTEM v3.1
   Playwright-first with selenium_code backward compatibility.
   With session state machine and session_state on messages.
   ================================================================= */

/* ------------------------------------------------------------------ */
/* Project                                                             */
/* ------------------------------------------------------------------ */

export interface Project {
  id: string;
  name: string;
  description?: string;
  base_url: string;
  tags?: string[];
  total_sessions?: number;
  last_test_at?: string;
  last_pass_rate?: number | null;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectRequest {
  name: string;
  base_url: string;
  description?: string;
  tags?: string[];
}

/* ------------------------------------------------------------------ */
/* Paginated Response                                                   */
/* ------------------------------------------------------------------ */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

/* ------------------------------------------------------------------ */
/* Session State Machine                                               */
/* ------------------------------------------------------------------ */

export type SessionState =
  | 'idle'
  | 'analyzing'
  | 'waiting_login'
  | 'login_done'
  | 'ready'
  | 'ready_to_generate'   // backend alias for 'ready'
  | 'generating'
  | 'tests_ready'
  | 'executing'
  | 'awaiting_approval'
  | 'completed';

/* ------------------------------------------------------------------ */
/* AI Chat                                                             */
/* ------------------------------------------------------------------ */

export interface ChatStatusResponse {
  groq_configured: boolean;
  model: string | null;
  active_browsers: number;
}

export type MessageRole = 'user' | 'assistant' | 'system';

export type MessageType =
  | 'text'
  | 'code'
  | 'test_result'
  | 'report'
  | 'error'
  | 'status';

export interface ChatMessage {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  message_type: MessageType;
  metadata?: Record<string, any>;
  created_at: string;
  /** State of the session at the time this message was sent. */
  session_state?: SessionState | null;
}

export interface ChatSession {
  id: string;
  title: string;
  project_id?: string;
  target_url?: string;
  is_active: boolean;
  state: SessionState;
  login_required: boolean;
  login_completed: boolean;
  browser_session_active?: boolean;
  page_analysis?: PageAnalysis;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  last_report_path?: string | null;
  /** Next page URL proposed after test execution completes. */
  next_proposed_url?: string | null;
  /** Remaining crawled links not yet tested. */
  untested_links?: string[];
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface ChatSessionListItem {
  id: string;
  title: string;
  target_url?: string;
  state: SessionState;
  message_count: number;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  created_at: string;
  updated_at: string;
}

/* ------------------------------------------------------------------ */
/* Page Analysis                                                       */
/* ------------------------------------------------------------------ */

export interface PageAnalysis {
  page_title: string;
  page_type: string;
  page_description?: string;
  key_features: string[];
  interactive_elements?: {
    forms?: any[];
    buttons?: any[];
    links?: any[];
    tables?: any[];
  };
  has_crud_operations: boolean;
  crud_details?: {
    can_create?: boolean;
    can_read?: boolean;
    can_update?: boolean;
    can_delete?: boolean;
  };
  technologies_detected: string[];
  accessibility_notes?: string[];
  potential_test_areas?: string[];
}

/* ------------------------------------------------------------------ */
/* Failure Analysis                                                    */
/* ------------------------------------------------------------------ */

export interface FailureAnalysis {
  root_cause: string;
  technical_details?: string;
  category: string;
  severity: string;
  what_happened?: string;
  what_should_have_happened?: string;
  why_it_failed?: string;
  impact?: string;
  steps_to_reproduce?: string[];
  suggested_fix: string;
  workaround?: string;
  regression_risk: string;
  additional_tests_needed?: string[];
}

/* ------------------------------------------------------------------ */
/* Generated Test                                                      */
/* ------------------------------------------------------------------ */

export type TestStatus =
  | 'pending'
  | 'running'
  | 'passed'
  | 'failed'
  | 'error'
  | 'skipped';

export interface GeneratedTest {
  id: string;
  test_name: string;
  test_category: string;
  priority: 'critical' | 'high' | 'medium' | 'low' | string;
  description?: string;
  preconditions?: string[];
  tags?: string[];
  suite_name?: string;
  steps: Record<string, any>[];
  expected_result: string;

  /**
   * Playwright test code (primary going forward).
   * Falls back to selenium_code for sessions generated before migration.
   */
  playwright_code?: string;

  /**
   * Legacy Selenium test code — kept for backward compatibility.
   * Prefer playwright_code for new sessions.
   */
  selenium_code?: string;

  is_destructive: boolean;
  destructive_reason?: string;

  status: TestStatus;
  actual_result?: string;
  error_message?: string;
  screenshot_path?: string;
  execution_time_ms?: number;
  failure_analysis?: FailureAnalysis;

  created_at: string;
  executed_at?: string;
}

/**
 * Returns the executable test code regardless of which field is populated.
 * Playwright takes priority; falls back to Selenium for legacy tests.
 */
export function getTestCode(test: GeneratedTest): string {
  return test.playwright_code ?? test.selenium_code ?? '';
}

/**
 * Returns a human-readable label for the code type stored on the test.
 */
export function getTestCodeLabel(test: GeneratedTest): 'Playwright' | 'Selenium' | 'None' {
  if (test.playwright_code) return 'Playwright';
  if (test.selenium_code)   return 'Selenium';
  return 'None';
}

/* ------------------------------------------------------------------ */
/* Request / Response Shapes                                           */
/* ------------------------------------------------------------------ */

export interface SendMessageRequest {
  session_id: string;
  content: string;
}

export interface AnalyzeUrlRequest {
  url: string;
  session_id: string;
}

export interface AnalyzeUrlResponse {
  session_id: string;
  url: string;
  state: SessionState;
  is_login_page: boolean;
  confidence: number;
  page_type: string;
  page_title: string;
  screenshot?: string;
}

export interface GenerateTestsRequest {
  url: string;
  session_id: string;
  additional_instructions?: string;
  html_content?: string;
}

export interface TestGenerationResponse {
  session_id: string;
  page_analysis?: PageAnalysis;
  test_cases: GeneratedTest[];
  total_tests: number;
}

export interface ExecuteTestsRequest {
  session_id: string;
  approved_destructive_ids?: string[];
  skip_destructive?: boolean;
}

export interface TestExecutionResponse {
  session_id: string;
  total_tests: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  pass_rate: number;
  execution_time_ms: number;
  report_path?: string;
  tests: GeneratedTest[];
}

export interface ApproveTestsRequest {
  session_id: string;
  approved_test_ids: string[];
}

/* ------------------------------------------------------------------ */
/* WebSocket message shapes                                            */
/* ------------------------------------------------------------------ */

export type WsMessageType =
  | 'ack'
  | 'token'
  | 'complete'
  | 'state_update'
  | 'error'
  | 'pong';

export interface WsIncomingMessage {
  type: WsMessageType;
  content?: string;
  state?: SessionState;
  message?: string;
}

export interface WsOutgoingMessage {
  content: string;
}

/* ------------------------------------------------------------------ */
/* Dashboard                                                           */
/* ------------------------------------------------------------------ */

export interface DashboardStats {
  total_projects: number;
  total_sessions: number;
  total_tests_run: number;
  passed_tests: number;
  failed_tests: number;
  overall_pass_rate: number;
  recent_projects: RecentProject[];
}

export interface RecentProject {
  id: string;
  name: string;
  base_url: string;
  last_pass_rate: number | null;
  updated_at: string | null;
}