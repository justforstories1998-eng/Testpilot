/* =================================================================
   TESTPILOT — API SERVICE v2.0
   Key fix: getOrCreateSession instead of always creating new
   ================================================================= */

import axios from 'axios';
import type {
  Project,
  CreateProjectRequest,
  PaginatedResponse,
  ChatStatusResponse,
  ChatSession,
  ChatSessionListItem,
  ChatMessage,
  GeneratedTest,
  AnalyzeUrlRequest,
  AnalyzeUrlResponse,
  GenerateTestsRequest,
  TestGenerationResponse,
  ExecuteTestsRequest,
  TestExecutionResponse,
  DashboardStats,
} from '../types';

/* ---- Axios instances ---- */
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const api = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

const longApi = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
  timeout: 600000,
});

/* ---- Error helper ---- */
export function extractError(e: any): string {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => {
        const field = d.loc
          ? d.loc.filter((_: any, i: number) => i > 0).join(' > ')
          : '';
        const msg = d.msg || String(d);
        return field ? `${field}: ${msg}` : msg;
      })
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.msg || JSON.stringify(detail);
  }
  return e?.message || 'An unexpected error occurred';
}

/* =============== Health =============== */
export const checkHealth = () =>
  api.get('/health').then((r) => r.data);

/* =============== Dashboard =============== */
export const getDashboardStats = () =>
  api.get<DashboardStats>('/dashboard').then((r) => r.data);

/* =============== Projects =============== */
export const listProjects = (params?: {
  page?: number;
  limit?: number;
  search?: string;
}) =>
  api
    .get<PaginatedResponse<Project>>('/projects', { params })
    .then((r) => r.data);

export const getProject = (id: string) =>
  api.get<Project>(`/projects/${id}`).then((r) => r.data);

export const createProject = (data: CreateProjectRequest) =>
  api.post<{ id: string; name: string; base_url: string }>(
    '/projects',
    data
  ).then((r) => r.data);

export const updateProject = (id: string, data: Partial<Project>) =>
  api.put<Project>(`/projects/${id}`, data).then((r) => r.data);

export const deleteProject = (id: string) =>
  api.delete(`/projects/${id}`).then((r) => r.data);

/* =============== AI Chat =============== */
export const chatApi = {
  /* Status */
  getStatus: () =>
    api.get<ChatStatusResponse>('/chat/status').then((r) => r.data),

  /* ============================================
   * THE KEY FIX: Get or create active session
   * This preserves chat history across page visits
   * ============================================ */
  getOrCreateSession: (projectId: string) =>
    api
      .get<ChatSession>('/chat/sessions/active', {
        params: { project_id: projectId },
      })
      .then((r) => r.data),

  /* Create explicit NEW session (user clicks "New Chat") */
  createNewSession: (projectId: string, targetUrl?: string) =>
    api
      .post<ChatSession>('/chat/sessions', null, {
        params: {
          project_id: projectId,
          ...(targetUrl ? { target_url: targetUrl } : {}),
        },
      })
      .then((r) => r.data),

  /* List all sessions for a project */
  listSessions: (projectId: string, limit = 50) =>
    api
      .get<ChatSessionListItem[]>('/chat/sessions', {
        params: { project_id: projectId, limit },
      })
      .then((r) => r.data),

  /* Get specific session with messages */
  getSession: (sessionId: string) =>
    api.get<ChatSession>(`/chat/sessions/${sessionId}`).then((r) => r.data),

  /* Delete session */
  deleteSession: (sessionId: string) =>
    api.delete(`/chat/sessions/${sessionId}`).then((r) => r.data),

  /* Send message */
  sendMessage: (content: string, sessionId: string) =>
    longApi
      .post<ChatMessage>('/chat/send', {
        content,
        session_id: sessionId,
      })
      .then((r) => r.data),

  /* Analyze URL */
  analyzeUrl: (data: AnalyzeUrlRequest) =>
    longApi.post<AnalyzeUrlResponse>('/chat/analyze-url', data).then((r) => r.data),

  /* Generate tests */
  generateTests: (data: GenerateTestsRequest) =>
    longApi.post<TestGenerationResponse>('/chat/generate-tests', data).then((r) => r.data),

  /* Execute tests */
  executeTests: (data: ExecuteTestsRequest) =>
    longApi.post<TestExecutionResponse>('/chat/execute-tests', data).then((r) => r.data),

  /* Approve destructive tests */
  approveAndRun: (sessionId: string, testIds: string[]) =>
    longApi
      .post('/chat/approve-and-run', {
        session_id: sessionId,
        approved_test_ids: testIds,
      })
      .then((r) => r.data),

  /* Get generated tests */
  getSessionTests: (sessionId: string) =>
    api.get<GeneratedTest[]>(`/chat/sessions/${sessionId}/tests`).then((r) => r.data),

  /* Report download URL */
  getReportDownloadUrl: (sessionId: string) =>
    `/api/v1/chat/report/${sessionId}`,
};

/* =============== Screenshot URL helper =============== */
export const getScreenshotUrl = (path: string) => {
  if (!path) return '';
  if (path.startsWith('/static/') || path.startsWith('http')) return path;
  const filename = path.split('/').pop() || path.split('\\').pop() || path;
  return `/static/screenshots/${filename}`;
};

export default api;