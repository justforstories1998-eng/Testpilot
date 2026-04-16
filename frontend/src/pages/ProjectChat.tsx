import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  FiPlus,
  FiArrowLeft,
  FiGlobe,
  FiPlay,
  FiTerminal,
  FiDownload,
  FiList,
  FiRefreshCw,
  FiCheckCircle,
  FiXCircle,
  FiAlertTriangle,
} from 'react-icons/fi';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import { getProject, chatApi, extractError } from '../services/api';
import { useChatWebSocket } from '../hooks/useWebSocket';
import type {
  Project,
  ChatSession,
  ChatMessage as ChatMessageType,
  ChatSessionListItem,
  SessionState,
} from '../types';
import toast from 'react-hot-toast';
import './ProjectChat.css';

/* ================================================================== */
/* TestExecutionProgress                                               */
/* ================================================================== */

interface ExecutionProgressProps {
  total:     number;
  passed:    number;
  failed:    number;
  errors:    number;
  isRunning: boolean;
}

const TestExecutionProgress: React.FC<ExecutionProgressProps> = ({
  total,
  passed,
  failed,
  errors,
  isRunning,
}) => {
  const completed  = passed + failed + errors;
  const progress   = total > 0 ? (completed / total) * 100 : 0;
  const passRate   = completed > 0 ? Math.round((passed / completed) * 100) : 0;

  // Hide when not running and nothing has been completed yet
  if (!isRunning && completed === 0) return null;

  return (
    <div className="execution-progress">
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="progress-stats">
        <span className="stat-pass">
          <FiCheckCircle size={12} /> {passed}
        </span>
        <span className="stat-fail">
          <FiXCircle size={12} /> {failed}
        </span>
        {errors > 0 && (
          <span className="stat-error">
            <FiAlertTriangle size={12} /> {errors}
          </span>
        )}
        <span className="stat-total">
          {completed}/{total}
        </span>
        {completed > 0 && (
          <span className="stat-rate">{passRate}%</span>
        )}
      </div>
    </div>
  );
};

/* ================================================================== */
/* ProjectChat                                                         */
/* ================================================================== */

const ProjectChat: React.FC = () => {
  const { projectId } = useParams();
  const navigate      = useNavigate();

  /* ── State ─────────────────────────────────────────────────────── */
  const [project,         setProject]         = useState<Project | null>(null);
  const [session,         setSession]         = useState<ChatSession | null>(null);
  const [messages,        setMessages]        = useState<ChatMessageType[]>([]);
  const [sessionList,     setSessionList]     = useState<ChatSessionListItem[]>([]);
  const [loading,         setLoading]         = useState(true);
  const [actionLoading,   setActionLoading]   = useState(false);
  const [isTyping,        setIsTyping]        = useState(false);
  const [streamingContent,setStreamingContent]= useState('');
  const [urlInput,        setUrlInput]        = useState('');
  const [showSessions,    setShowSessions]    = useState(false);

  /* Execution progress — populated while state === 'executing' */
  const [execProgress, setExecProgress] = useState({
    total:  0,
    passed: 0,
    failed: 0,
    errors: 0,
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);

  /* ── Init ───────────────────────────────────────────────────────── */
  useEffect(() => {
    if (!projectId) return;

    const init = async () => {
      setLoading(true);
      try {
        const proj  = await getProject(projectId);
        setProject(proj);

        const sess = await chatApi.getOrCreateSession(projectId);
        setSession(sess);
        setMessages(sess.messages);

        const sessions = await chatApi.listSessions(projectId);
        setSessionList(sessions);
      } catch {
        toast.error('Failed to load project');
        navigate('/projects');
      } finally {
        setLoading(false);
      }
    };

    init();
  }, [projectId, navigate]);

  /* ── Auto-scroll ────────────────────────────────────────────────── */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  /* ── Reset progress when execution starts / finishes ───────────── */
  useEffect(() => {
    if (session?.state !== 'executing') return;
    setExecProgress({ total: session.total_tests ?? 0, passed: 0, failed: 0, errors: 0 });
  }, [session?.state, session?.total_tests]);

  /* ── Reload session ─────────────────────────────────────────────── */
  const reloadSession = useCallback(async () => {
    if (!session) return;
    try {
      const updated = await chatApi.getSession(session.id);
      setSession(updated);
      setMessages(updated.messages);

      // Sync execution progress from completed session
      if (updated.state === 'completed') {
        setExecProgress({
          total:  updated.total_tests  ?? 0,
          passed: updated.passed_tests ?? 0,
          failed: updated.failed_tests ?? 0,
          errors: 0,
        });
      }
    } catch {
      // silently ignore refresh failures
    }
  }, [session]);

  /* ── WebSocket ──────────────────────────────────────────────────── */
  const { isConnected, sendMessage: wsSend } = useChatWebSocket({
    sessionId: session?.id ?? null,
    callbacks: {
      onToken: (token) => {
        setStreamingContent((prev) => prev + token);
      },

      onComplete: (finalContent) => {
        if (finalContent) {
          setMessages((prev) => [
            ...prev,
            {
              id:           `msg_${Date.now()}`,
              session_id:   session?.id ?? '',
              role:         'assistant',
              content:      finalContent,
              message_type: 'text',
              created_at:   new Date().toISOString(),
            },
          ]);
        }
        setStreamingContent('');
        setIsTyping(false);
        reloadSession();
      },

      onError: (err) => {
        toast.error('Error: ' + err);
        setIsTyping(false);
        setStreamingContent('');
      },
    },
  });

  /* ── Switch session ─────────────────────────────────────────────── */
  const switchSession = async (sessionId: string) => {
    try {
      const sess = await chatApi.getSession(sessionId);
      setSession(sess);
      setMessages(sess.messages);
      setShowSessions(false);
    } catch {
      toast.error('Failed to load session');
    }
  };

  /* ── New session ────────────────────────────────────────────────── */
  const handleNewSession = async () => {
    if (!project) return;
    try {
      const newSess = await chatApi.createNewSession(project.id, project.base_url);
      setSession(newSess);
      setMessages(newSess.messages);

      const sessions = await chatApi.listSessions(project.id);
      setSessionList(sessions);
    } catch {
      toast.error('Failed to create session');
    }
  };

  /* ── Send message ───────────────────────────────────────────────── */
  const handleSend = async (content: string) => {
    if (!session) return;

    const userMsg: ChatMessageType = {
      id:           `temp_${Date.now()}`,
      session_id:   session.id,
      role:         'user',
      content,
      message_type: 'text',
      created_at:   new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);

    try {
      if (isConnected) {
        wsSend(content);
      } else {
        // HTTP fallback
        const res = await chatApi.sendMessage(content, session.id);
        setMessages((prev) => [...prev, res]);
        setIsTyping(false);

        if (res.session_state) {
          setSession((prev) =>
            prev ? { ...prev, state: res.session_state! } : prev
          );
        }
        await reloadSession();
      }
    } catch (err) {
      toast.error(extractError(err));
      setIsTyping(false);
    }
  };

  /* ── Analyze URL ────────────────────────────────────────────────── */
  const handleAnalyzeUrl = async () => {
    if (!session || !urlInput.trim()) return;

    let url = urlInput.trim();
    if (!url.startsWith('http')) url = 'https://' + url;

    setActionLoading(true);
    try {
      await chatApi.analyzeUrl({ url, session_id: session.id });
      await reloadSession();
      setUrlInput('');
    } catch (err) {
      toast.error(extractError(err));
    } finally {
      setActionLoading(false);
    }
  };

  /* ── Generate tests ─────────────────────────────────────────────── */
  const handleGenerateTests = async () => {
    if (!session?.target_url) {
      toast.error('Analyze a URL first');
      return;
    }
    setActionLoading(true);
    try {
      await chatApi.generateTests({
        url:        session.target_url,
        session_id: session.id,
      });
      await reloadSession();
    } catch (err) {
      toast.error(extractError(err));
    } finally {
      setActionLoading(false);
    }
  };

  /* ── Execute tests ──────────────────────────────────────────────── */
  const handleExecuteTests = async () => {
    if (!session) return;

    // Optimistically show the progress bar immediately
    setExecProgress({
      total:  session.total_tests ?? 0,
      passed: 0,
      failed: 0,
      errors: 0,
    });
    setActionLoading(true);

    try {
      const result = await chatApi.executeTests({
        session_id:      session.id,
        skip_destructive: true,
      });

      // Populate final progress from execution result
      setExecProgress({
        total:  result.total_tests,
        passed: result.passed,
        failed: result.failed,
        errors: result.errors,
      });

      await reloadSession();
    } catch (err) {
      toast.error(extractError(err));
    } finally {
      setActionLoading(false);
    }
  };

  /* ── Approve destructive ────────────────────────────────────────── */
  const handleApproveDestructive = async (testIds: string[]) => {
    if (!session) return;
    setActionLoading(true);
    try {
      await chatApi.approveAndRun(session.id, testIds);
      await reloadSession();
    } catch (err) {
      toast.error(extractError(err));
    } finally {
      setActionLoading(false);
    }
  };

  /* ── Action bar ─────────────────────────────────────────────────── */
  const renderActionBar = () => {
    if (!session) return null;
    const state = session.state as SessionState;
    const isExecuting = state === 'executing' || actionLoading;

    return (
      <div className="action-bar glass-static">

        {/* URL input — idle / ready / completed */}
        {(state === 'idle' || state === 'ready' || state === 'completed') && (
          <div className="url-analyze-row">
            <div className="url-input-group">
              <FiGlobe className="url-icon" />
              <input
                type="text"
                className="url-input"
                placeholder="Enter URL to analyze..."
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyzeUrl()}
                disabled={actionLoading}
              />
            </div>
            <button
              className="btn-primary btn-sm"
              onClick={handleAnalyzeUrl}
              disabled={actionLoading || !urlInput.trim()}
            >
              {actionLoading
                ? <FiRefreshCw className="spin" />
                : <FiGlobe size={14} />}
              Analyze
            </button>
          </div>
        )}

        {/* Waiting for login */}
        {state === 'waiting_login' && (
          <div className="state-hint">
            <span className="state-badge waiting">Waiting for Login</span>
            <span className="state-text">
              Log in via the browser window, then type <strong>done</strong>
            </span>
          </div>
        )}

        {/* Generate Tests */}
        {(state === 'ready' || state === 'login_done' || state === 'completed')
          && session.target_url && (
          <button
            className="btn-primary"
            onClick={handleGenerateTests}
            disabled={actionLoading}
          >
            {actionLoading
              ? <FiRefreshCw className="spin" />
              : <FiTerminal size={14} />}
            Generate Tests
          </button>
        )}

        {/* Run Tests */}
        {(state === 'tests_ready' || state === 'awaiting_approval') && (
          <button
            className="btn-primary"
            onClick={handleExecuteTests}
            disabled={actionLoading}
          >
            {actionLoading
              ? <FiRefreshCw className="spin" />
              : <FiPlay size={14} />}
            Run Tests
          </button>
        )}

        {/* Execution progress bar */}
        {(state === 'executing' || state === 'completed') && (
          <TestExecutionProgress
            total={execProgress.total}
            passed={execProgress.passed}
            failed={execProgress.failed}
            errors={execProgress.errors}
            isRunning={isExecuting}
          />
        )}

        {/* Executing spinner */}
        {state === 'executing' && (
          <div className="state-hint">
            <span className="state-badge running">Tests Running</span>
            <FiRefreshCw className="spin" />
          </div>
        )}

        {/* Download report */}
        {state === 'completed' && session.last_report_path && (
          <a
            href={chatApi.getReportDownloadUrl(session.id)}
            className="btn-secondary btn-sm"
            download
            target="_blank"
            rel="noreferrer"
          >
            <FiDownload size={14} /> Download Report
          </a>
        )}
      </div>
    );
  };

  /* ── Loading screen ─────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="full-loader">
        <div className="spinner-lg" />
      </div>
    );
  }

  /* ── Render ─────────────────────────────────────────────────────── */
  return (
    <div className="chat-layout">

      {/* Session Sidebar */}
      <div className={`chat-sidebar ${showSessions ? 'open' : ''}`}>
        <div className="chat-sidebar-header">
          <button
            className="btn-secondary sidebar-new-btn"
            onClick={handleNewSession}
          >
            <FiPlus size={14} /> New Chat
          </button>
        </div>

        <div className="chat-session-list">
          {sessionList.map((s) => (
            <div
              key={s.id}
              className={`session-list-item ${s.id === session?.id ? 'active' : ''}`}
              onClick={() => switchSession(s.id)}
            >
              <div className="session-list-title">{s.title}</div>
              <div className="session-list-meta">
                <span>{s.message_count} msgs</span>
                {s.total_tests > 0 && (
                  <span
                    className={`session-list-badge ${
                      s.passed_tests === s.total_tests ? 'pass' : 'mixed'
                    }`}
                  >
                    {s.passed_tests}/{s.total_tests}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="chat-main">

        {/* Header */}
        <header className="chat-header glass-static">
          <div className="header-left">
            <button className="btn-icon" onClick={() => navigate('/projects')}>
              <FiArrowLeft />
            </button>
            <button
              className="btn-icon mobile-sessions-toggle"
              onClick={() => setShowSessions(!showSessions)}
            >
              <FiList />
            </button>
            <div>
              <h2 className="chat-title">{project?.name}</h2>
              <span className="chat-subtitle">
                {session?.target_url || project?.base_url || 'No URL'}
              </span>
            </div>
          </div>

          <div className="header-right">
            {session && (
              <span className={`state-indicator state-${session.state}`}>
                {session.state.replace(/_/g, ' ')}
              </span>
            )}
            <div className={`connection-dot ${isConnected ? 'connected' : ''}`} />
          </div>
        </header>

        {/* Action Bar */}
        {renderActionBar()}

        {/* Messages */}
        <div className="messages-container">
          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              sessionState={session?.state ?? 'idle'}
              onGenerate={handleGenerateTests}
              onRun={handleExecuteTests}
              onApprove={handleApproveDestructive}
            />
          ))}

          {/* Streaming bubble */}
          {streamingContent && (
            <ChatMessage
              message={{
                id:           'streaming',
                session_id:   session?.id ?? '',
                role:         'assistant',
                content:      streamingContent,
                message_type: 'text',
                created_at:   new Date().toISOString(),
              }}
              sessionState={session?.state ?? 'idle'}
              isStreaming
            />
          )}

          {/* Typing indicator */}
          {isTyping && !streamingContent && (
            <div className="message-row assistant">
              <div className="avatar assistant-avatar">
                <FiTerminal size={16} />
              </div>
              <div className="typing-bubble glass-static">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="input-area">
          <div className="input-wrapper glass-static">
            <ChatInput
              onSend={handleSend}
              disabled={isTyping || actionLoading}
              placeholder={
                session?.state === 'waiting_login'
                  ? 'Type "done" when you have finished logging in...'
                  : 'Type a message, describe a test, or ask about testing...'
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProjectChat;