import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  FiUser, FiTerminal, FiCheckCircle, FiXCircle,
  FiAlertTriangle, FiDownload, FiPlay, FiCode,
  FiShield, FiClock, FiTrendingUp,
} from 'react-icons/fi';
import { chatApi } from '../services/api';
import type { ChatMessage as ChatMessageType, SessionState } from '../types';
import './ChatMessage.css';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

interface ChatMessageProps {
  message: ChatMessageType;
  sessionState: SessionState;
  isStreaming?: boolean;
  onGenerate?: () => void;
  onRun?: () => void;
  onApprove?: (ids: string[]) => void;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function getPassRateColor(rate: number): string {
  if (rate >= 90) return '#22c55e';
  if (rate >= 50) return '#f59e0b';
  return '#ef4444';
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  sessionState,
  isStreaming,
  onGenerate,
  onRun,
  onApprove,
}) => {
  const isUser       = message.role         === 'user';
  const isError      = message.message_type === 'error';
  const isReport     = message.message_type === 'report';
  const isTestResult = message.message_type === 'test_result';

  const meta             = message.metadata ?? {};
  const resultsSummary   = meta.results_summary as Record<string, any> | undefined;
  const destructiveTests = (meta.destructive_pending ?? []) as any[];

  /* ── Markdown code-block renderer ─────────────────────────────── */
  const renderCode = ({ children, className, ...rest }: any) => {
    const match = /language-(\w+)/.exec(className ?? '');
    return match ? (
      <div className="code-block-wrapper">
        <div className="code-header">
          <FiCode size={12} />
          <span>{match[1]}</span>
        </div>
        <SyntaxHighlighter
          {...rest}
          style={vscDarkPlus}
          language={match[1]}
          PreTag="div"
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      </div>
    ) : (
      <code {...rest} className={className}>
        {children}
      </code>
    );
  };

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <div className={`message-row ${message.role}${isError ? ' error-row' : ''}`}>

      {/* Avatar */}
      <div className={`avatar ${isUser ? 'user-avatar' : 'assistant-avatar'}`}>
        {isUser ? <FiUser size={14} /> : <FiTerminal size={14} />}
      </div>

      {/* Bubble */}
      <div
        className={[
          'message-bubble',
          isUser ? 'user-bubble' : 'assistant-bubble',
          isStreaming ? 'streaming' : '',
        ].filter(Boolean).join(' ')}
      >
        {/* Markdown body */}
        <div className="markdown-content">
          <ReactMarkdown components={{ code: renderCode }}>
            {message.content}
          </ReactMarkdown>
        </div>

        {/* ── Test Generation Summary card ───────────────────────── */}
        {isTestResult && meta.test_count != null && (
          <div className="inline-card">
            <div className="inline-stat-row">
              <span className="inline-stat">
                <FiCheckCircle size={14} />
                {meta.test_count} tests generated
              </span>

              {(meta.destructive_count ?? 0) > 0 && (
                <span className="inline-stat destructive">
                  <FiShield size={14} />
                  {meta.destructive_count} require approval
                </span>
              )}
            </div>

            {(sessionState === 'tests_ready' ||
              sessionState === 'awaiting_approval') && (
              <button className="btn-primary btn-sm" onClick={onRun}>
                <FiPlay size={14} /> Run All Tests
              </button>
            )}
          </div>
        )}

        {/* ── Execution Report card ──────────────────────────────── */}
        {isReport && resultsSummary != null && (
          <div className="inline-card report-card">

            {/* Header */}
            <div className="report-header">
              <FiTrendingUp size={16} />
              <span className="report-title">Test Execution Report</span>
            </div>

            {/* Stats row */}
            <div className="report-stats-row">
              <span className="report-stat pass">
                <FiCheckCircle size={13} />
                {resultsSummary.passed} Passed
              </span>

              <span className="report-stat fail">
                <FiXCircle size={13} />
                {resultsSummary.failed} Failed
              </span>

              {(resultsSummary.errors ?? 0) > 0 && (
                <span className="report-stat error">
                  <FiAlertTriangle size={13} />
                  {resultsSummary.errors} Errors
                </span>
              )}

              <span
                className="report-stat rate"
                style={{
                  color: getPassRateColor(resultsSummary.pass_rate ?? 0),
                }}
              >
                {resultsSummary.pass_rate ?? 0}% Pass Rate
              </span>
            </div>

            {/* Timing */}
            {meta.execution_time_ms != null && (
              <div className="report-timing">
                <FiClock size={12} />
                {(meta.execution_time_ms / 1000).toFixed(1)}s execution time
              </div>
            )}

            {/* Download */}
            {meta.report_path && (
              <a
                href={chatApi.getReportDownloadUrl(message.session_id)}
                className="btn-secondary btn-sm report-download-btn"
                download
                target="_blank"
                rel="noreferrer"
              >
                <FiDownload size={14} /> Download Detailed Report (Excel)
              </a>
            )}

            {/* Destructive approval */}
            {destructiveTests.length > 0 && (
              <div className="destructive-section">
                <div className="destructive-header">
                  <FiShield size={14} />
                  Approval Required for Destructive Tests
                </div>

                <ul className="destructive-list">
                  {destructiveTests.map((t: any) => (
                    <li key={t.test_id}>
                      <strong>{t.test_name}</strong> — {t.reason}
                    </li>
                  ))}
                </ul>

                <button
                  className="btn-danger btn-sm"
                  onClick={() =>
                    onApprove?.(destructiveTests.map((t: any) => t.test_id))
                  }
                >
                  <FiShield size={14} /> Approve &amp; Run Destructive Tests
                </button>
              </div>
            )}
          </div>
        )}

        {/* Streaming cursor */}
        {isStreaming && <span className="streaming-cursor" />}
      </div>
    </div>
  );
};

export default ChatMessage;