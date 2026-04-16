import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FiPlus,
  FiActivity,
  FiCheckCircle,
  FiFolder,
  FiArrowRight,
  FiTarget,
} from 'react-icons/fi';
import { getDashboardStats } from '../services/api';
import type { DashboardStats } from '../types';

/* ------------------------------------------------------------------ */
/* Inline styles — avoids the missing-CSS-module TS error entirely     */
/* and keeps the component fully self-contained.                       */
/* ------------------------------------------------------------------ */

const styles: Record<string, React.CSSProperties> = {
  /* Layout */
  dashboard: {
    padding: '2rem',
    maxWidth: '1200px',
    margin: '0 auto',
  },
  loading: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '60vh',
    gap: '1rem',
    color: 'var(--text-muted)',
  },

  /* Header */
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: '2rem',
    gap: '1rem',
    flexWrap: 'wrap' as const,
  },
  headerTitle: {
    margin: 0,
    fontSize: '1.75rem',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  headerSub: {
    margin: '0.25rem 0 0',
    fontSize: '0.875rem',
    color: 'var(--text-muted)',
  },

  /* Stats grid */
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '1rem',
    marginBottom: '2.5rem',
  },
  card: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    padding: '1.25rem',
    borderRadius: 'var(--radius-lg)',
    background: 'var(--bg-card)',
    border: '1px solid var(--glass-border)',
  },
  cardIcon: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '2.5rem',
    height: '2.5rem',
    borderRadius: 'var(--radius-md)',
    flexShrink: 0,
  },
  cardValue: {
    display: 'block',
    fontSize: '1.75rem',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1,
  },
  cardLabel: {
    display: 'block',
    fontSize: '0.8rem',
    color: 'var(--text-muted)',
    marginTop: '0.2rem',
  },

  /* Section */
  section: {
    marginBottom: '2rem',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '1rem',
  },
  sectionTitle: {
    margin: 0,
    fontSize: '1.1rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },

  /* Projects grid */
  projectsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '1rem',
  },
  projectCard: {
    padding: '1.25rem',
    borderRadius: 'var(--radius-lg)',
    background: 'var(--bg-card)',
    border: '1px solid var(--glass-border)',
    cursor: 'pointer',
    transition: 'border-color 0.15s, transform 0.15s',
  },
  projectCardTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '0.4rem',
  },
  projectName: {
    margin: 0,
    fontSize: '0.95rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  projectUrl: {
    margin: '0 0 0.75rem',
    fontSize: '0.78rem',
    color: 'var(--text-muted)',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  projectFooter: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '0.78rem',
  },
  projectDate: {
    color: 'var(--text-tertiary)',
  },

  /* Empty state */
  empty: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '1rem',
    padding: '3rem',
    borderRadius: 'var(--radius-lg)',
    background: 'var(--bg-card)',
    border: '1px solid var(--glass-border)',
    color: 'var(--text-muted)',
    textAlign: 'center' as const,
  },
};

/* Icon background colours */
const iconBg: Record<string, React.CSSProperties> = {
  blue:   { background: 'rgba(99, 102, 241, 0.15)', color: 'var(--accent-primary)' },
  purple: { background: 'rgba(168, 85, 247, 0.15)', color: '#a855f7' },
  green:  { background: 'rgba(34, 197, 94, 0.15)',  color: 'var(--success)' },
  red:    { background: 'rgba(239, 68, 68, 0.15)',   color: 'var(--error)' },
};

/* Pass-rate badge colour */
function rateColor(rate: number): React.CSSProperties {
  return {
    fontSize: '0.78rem',
    fontWeight: 600,
    color: rate >= 80 ? 'var(--success)' : 'var(--error)',
  };
}

/* ------------------------------------------------------------------ */
/* Default stats (used while loading or on error)                      */
/* ------------------------------------------------------------------ */

const EMPTY_STATS: DashboardStats = {
  total_projects:    0,
  total_sessions:    0,
  total_tests_run:   0,
  passed_tests:      0,
  failed_tests:      0,
  overall_pass_rate: 0,
  recent_projects:   [],
};

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  const [stats,   setStats]   = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await getDashboardStats();
        if (!cancelled) setStats(data);
      } catch (err) {
        console.error('Dashboard load failed:', err);
        if (!cancelled) setError('Could not load dashboard stats.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, []);

  /* ── Loading ──────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div style={styles.loading}>
        <div className="spinner spinner-lg" />
        <p>Loading dashboard…</p>
      </div>
    );
  }

  const s = stats ?? EMPTY_STATS;

  /* ── Render ───────────────────────────────────────────────────── */
  return (
    <div style={styles.dashboard} className="animate-fade">

      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.headerTitle}>Dashboard</h1>
          <p style={styles.headerSub}>Overview of your automated testing</p>
        </div>
        <button className="btn-primary" onClick={() => navigate('/projects')}>
          <FiPlus size={16} />
          <span>New Project</span>
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div
          style={{
            padding: '0.75rem 1rem',
            marginBottom: '1.5rem',
            borderRadius: 'var(--radius-md)',
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.25)',
            color: 'var(--error)',
            fontSize: '0.875rem',
          }}
        >
          {error}
        </div>
      )}

      {/* Stats grid */}
      <div style={styles.grid}>
        {/* Projects */}
        <div style={styles.card}>
          <div style={{ ...styles.cardIcon, ...iconBg.blue }}>
            <FiFolder size={20} />
          </div>
          <div>
            <span style={styles.cardValue}>{s.total_projects}</span>
            <span style={styles.cardLabel}>Projects</span>
          </div>
        </div>

        {/* Tests run */}
        <div style={styles.card}>
          <div style={{ ...styles.cardIcon, ...iconBg.purple }}>
            <FiActivity size={20} />
          </div>
          <div>
            <span style={styles.cardValue}>{s.total_tests_run}</span>
            <span style={styles.cardLabel}>Tests Run</span>
          </div>
        </div>

        {/* Passed */}
        <div style={styles.card}>
          <div style={{ ...styles.cardIcon, ...iconBg.green }}>
            <FiCheckCircle size={20} />
          </div>
          <div>
            <span style={styles.cardValue}>{s.passed_tests}</span>
            <span style={styles.cardLabel}>Passed</span>
          </div>
        </div>

        {/* Pass rate */}
        <div style={styles.card}>
          <div style={{ ...styles.cardIcon, ...iconBg.red }}>
            <FiTarget size={20} />
          </div>
          <div>
            <span style={styles.cardValue}>{s.overall_pass_rate}%</span>
            <span style={styles.cardLabel}>Pass Rate</span>
          </div>
        </div>
      </div>

      {/* Recent projects */}
      <div style={styles.section}>
        <div style={styles.sectionHeader}>
          <h2 style={styles.sectionTitle}>Recent Projects</h2>
          <button className="btn-ghost" onClick={() => navigate('/projects')}>
            View all
          </button>
        </div>

        {s.recent_projects.length === 0 ? (
          <div style={styles.empty}>
            <FiFolder size={40} />
            <p style={{ margin: 0 }}>No projects yet. Create one to get started.</p>
            <button
              className="btn-secondary"
              onClick={() => navigate('/projects')}
            >
              Create Project
            </button>
          </div>
        ) : (
          <div style={styles.projectsGrid}>
            {s.recent_projects.map((p) => (
              <div
                key={p.id}
                style={styles.projectCard}
                className="card-3d"
                onClick={() => navigate(`/project/${p.id}`)}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor =
                    'var(--accent-primary)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.borderColor =
                    'var(--glass-border)';
                }}
              >
                <div style={styles.projectCardTop}>
                  <h3 style={styles.projectName}>{p.name}</h3>
                  <FiArrowRight
                    size={16}
                    style={{ color: 'var(--text-muted)', flexShrink: 0 }}
                  />
                </div>

                <p style={styles.projectUrl}>{p.base_url}</p>

                <div style={styles.projectFooter}>
                  {p.last_pass_rate !== null &&
                   p.last_pass_rate !== undefined && (
                    <span style={rateColor(p.last_pass_rate)}>
                      {p.last_pass_rate}% pass rate
                    </span>
                  )}
                  {p.updated_at && (
                    <span style={styles.projectDate}>
                      {new Date(p.updated_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;