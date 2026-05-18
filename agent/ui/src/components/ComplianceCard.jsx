/**
 * Workstream E — ComplianceCard: Inline compliance results rendered inside chat bubbles.
 * Triggered when the pipeline detects a compliance intent from natural language.
 * Streams SSE findings and renders a verdict summary + expandable findings register.
 */
import React, { useState, useEffect, useRef } from 'react';
import { ShieldCheck, ShieldAlert, ShieldX, ChevronDown, ChevronUp, Download, Loader2 } from 'lucide-react';
import api, { getApiUrl } from '../utils/api';

const VERDICT_COLORS = {
  'Compliant':      { bg: 'rgba(34, 197, 94, 0.12)', border: '#22c55e', icon: '✅' },
  'Non-Compliant':  { bg: 'rgba(255, 69, 0, 0.12)',  border: '#ff4500', icon: '❌' },
  'Partial':        { bg: 'rgba(245, 158, 11, 0.12)', border: '#f59e0b', icon: '⚠️' },
  'Missing':        { bg: 'rgba(168, 85, 247, 0.12)', border: '#a855f7', icon: '🔍' },
  'Contradiction':  { bg: 'rgba(239, 68, 68, 0.12)',  border: '#ef4444', icon: '⚡' },
  'Unverifiable':   { bg: 'rgba(100, 116, 139, 0.12)', border: '#64748b', icon: '❓' },
};

const SEVERITY_COLORS = {
  'Critical': '#ff4500',
  'Major':    '#f59e0b',
  'Minor':    '#22c55e',
  'None':     '#64748b',
};

export default function ComplianceCard({ intentParams, token }) {
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    runComplianceCheck();
  }, []);

  const runComplianceCheck = async () => {
    const { subject_doc_ids, standard_doc_ids, check_scope } = intentParams;
    try {
      const apiUrl = getApiUrl('');
      const resp = await fetch(`${apiUrl}/api/agent/compliance/check`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ subject_doc_ids, standard_doc_ids, check_scope }),
      });

      if (!resp.ok) throw new Error(`Compliance check failed: ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.finding) {
              setFindings(prev => [...prev, data.finding]);
            }
            if (data.done) {
              setSummary(data.summary);
              setDownloadUrl(data.download_url);
              setLoading(false);
            }
          } catch { /* skip malformed SSE */ }
        }
      }
      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const toggleFinding = (i) => setExpanded(prev => ({ ...prev, [i]: !prev[i] }));

  const apiUrl = getApiUrl('');

  return (
    <div style={styles.card}>
      {/* Header */}
      <div style={styles.header}>
        <ShieldCheck size={18} color="var(--primary)" />
        <span style={styles.title}>Compliance Analysis</span>
        {loading && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent-amber)' }} />}
      </div>

      {error && (
        <div style={styles.error}>
          <ShieldX size={14} /> {error}
        </div>
      )}

      {/* Summary Bar */}
      {summary && (
        <div style={styles.summaryBar}>
          <div style={styles.scoreCircle}>
            <span style={{ fontSize: '18px', fontWeight: 800, color: summary.score >= 70 ? '#22c55e' : '#ff4500' }}>
              {summary.score}%
            </span>
            <span style={{ fontSize: '9px', color: 'var(--text-muted)' }}>Score</span>
          </div>
          <div style={styles.summaryMeta}>
            <div style={{
              ...styles.recommendation,
              background: summary.recommendation === 'APPROVE' ? 'rgba(34,197,94,0.15)' : summary.recommendation === 'REJECT' ? 'rgba(255,69,0,0.15)' : 'rgba(245,158,11,0.15)',
              color: summary.recommendation === 'APPROVE' ? '#22c55e' : summary.recommendation === 'REJECT' ? '#ff4500' : '#f59e0b',
            }}>
              {summary.recommendation}
            </div>
            <div style={styles.statsRow}>
              <span style={{ color: '#22c55e' }}>✅ {summary.compliant}</span>
              <span style={{ color: '#ff4500' }}>❌ {summary.non_compliant}</span>
              <span style={{ color: '#f59e0b' }}>⚠️ {summary.partial}</span>
              <span style={{ color: '#a855f7' }}>🔍 {summary.missing}</span>
            </div>
          </div>
          {downloadUrl && (
            <a
              href={`${apiUrl}${downloadUrl}?token=${encodeURIComponent(token || '')}`}
              style={styles.downloadBtn}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={13} /> Report
            </a>
          )}
        </div>
      )}

      {/* Findings List */}
      {findings.length > 0 && (
        <div style={styles.findingsList}>
          {findings.map((f, i) => {
            const vc = VERDICT_COLORS[f.verdict] || VERDICT_COLORS['Unverifiable'];
            const sc = SEVERITY_COLORS[f.severity] || SEVERITY_COLORS['None'];
            const isOpen = expanded[i];
            return (
              <div key={i} style={{ ...styles.finding, background: vc.bg, borderLeftColor: vc.border }}>
                <div style={styles.findingHeader} onClick={() => toggleFinding(i)}>
                  <span style={{ fontSize: '13px' }}>{vc.icon}</span>
                  <span style={styles.clauseId}>{f.clause_id || 'N/A'}</span>
                  <span style={styles.findingTopic}>{f.topic}</span>
                  <span style={{ ...styles.severityBadge, color: sc, borderColor: sc }}>{f.severity}</span>
                  <span style={{ ...styles.verdictBadge, color: vc.border }}>{f.verdict}</span>
                  {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </div>
                {isOpen && (
                  <div style={styles.findingBody}>
                    <div><strong>Requirement:</strong> {f.requirement}</div>
                    <div><strong>Criterion:</strong> {f.acceptance_criterion}</div>
                    <div><strong>Finding:</strong> {f.finding}</div>
                    {f.recommendation && <div><strong>Recommendation:</strong> {f.recommendation}</div>}
                    {f.citation && f.citation !== 'N/A' && (
                      <div style={styles.citation}>"{f.citation}"</div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {loading && findings.length === 0 && (
        <div style={styles.loadingState}>
          <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} />
          <span>Analyzing compliance…</span>
        </div>
      )}
    </div>
  );
}

const styles = {
  card: {
    marginTop: '10px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg, 12px)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: '8px',
    padding: '12px 14px',
    borderBottom: '1px solid var(--border)',
    fontSize: '13px', fontWeight: 700,
    color: 'var(--text-primary)',
  },
  title: { flex: 1 },
  error: {
    display: 'flex', alignItems: 'center', gap: '6px',
    padding: '10px 14px',
    color: '#ff4500', fontSize: '12px',
    background: 'rgba(255,69,0,0.08)',
  },
  summaryBar: {
    display: 'flex', alignItems: 'center', gap: '14px',
    padding: '14px',
    borderBottom: '1px solid var(--border)',
  },
  scoreCircle: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center',
    width: 56, height: 56,
    borderRadius: '50%',
    background: 'var(--bg-surface)',
    border: '2px solid var(--border)',
    flexShrink: 0,
  },
  summaryMeta: {
    display: 'flex', flexDirection: 'column', gap: '6px', flex: 1,
  },
  recommendation: {
    display: 'inline-block',
    padding: '3px 10px',
    borderRadius: '6px',
    fontSize: '11px', fontWeight: 700,
    letterSpacing: '0.5px',
    width: 'fit-content',
  },
  statsRow: {
    display: 'flex', gap: '10px', fontSize: '11px', fontWeight: 500,
  },
  downloadBtn: {
    display: 'flex', alignItems: 'center', gap: '5px',
    padding: '6px 12px',
    background: 'var(--primary)',
    color: '#fff',
    borderRadius: '6px',
    fontSize: '11px', fontWeight: 600,
    textDecoration: 'none',
    flexShrink: 0,
  },
  findingsList: {
    display: 'flex', flexDirection: 'column', gap: '1px',
    maxHeight: '400px', overflowY: 'auto',
  },
  finding: {
    borderLeft: '3px solid',
    transition: 'background 0.15s',
  },
  findingHeader: {
    display: 'flex', alignItems: 'center', gap: '8px',
    padding: '8px 12px',
    cursor: 'pointer',
    fontSize: '12px',
    color: 'var(--text-primary)',
  },
  clauseId: {
    fontWeight: 700, fontSize: '11px',
    color: 'var(--primary)',
    minWidth: '60px',
  },
  findingTopic: {
    flex: 1, fontSize: '12px',
    color: 'var(--text-secondary)',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  severityBadge: {
    fontSize: '9px', fontWeight: 700,
    padding: '1px 6px',
    borderRadius: '4px',
    border: '1px solid',
    textTransform: 'uppercase',
  },
  verdictBadge: {
    fontSize: '10px', fontWeight: 600,
  },
  findingBody: {
    padding: '8px 12px 12px 22px',
    fontSize: '12px',
    color: 'var(--text-secondary)',
    lineHeight: '1.6',
    display: 'flex', flexDirection: 'column', gap: '4px',
  },
  citation: {
    fontStyle: 'italic',
    color: 'var(--text-muted)',
    fontSize: '11px',
    padding: '4px 8px',
    borderLeft: '2px solid var(--border)',
    marginTop: '4px',
  },
  loadingState: {
    display: 'flex', alignItems: 'center', gap: '8px',
    padding: '20px',
    justifyContent: 'center',
    color: 'var(--text-muted)',
    fontSize: '13px',
  },
};
