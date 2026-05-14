/**
 * AGRA Phase D4 — ComparisonCard
 * Renders structured branch-isolated bid comparison results with
 * branch badges, compliance matrix, executive summary, and recommendation.
 */

import { useState } from 'react';
import {
  Trophy, FileDown, ShieldCheck, AlertTriangle, XCircle,
  CheckCircle, MinusCircle, ChevronDown, ChevronUp, GitCompare,
  Clock, Users,
} from 'lucide-react';

const VERDICT_META = {
  compliant:      { label: 'Compliant',       color: '#16a34a', bg: 'rgba(22,163,74,0.08)', icon: CheckCircle },
  partial:        { label: 'Partial',         color: '#ca8a04', bg: 'rgba(202,138,4,0.08)',  icon: MinusCircle },
  non_compliant:  { label: 'Non-Compliant',   color: '#dc2626', bg: 'rgba(220,38,38,0.08)',  icon: XCircle },
  insufficient_evidence: { label: 'Insufficient', color: '#6b7280', bg: 'rgba(107,114,128,0.08)', icon: AlertTriangle },
};

const SEVERITY_META = {
  low:    { color: '#16a34a', label: 'Low' },
  medium: { color: '#ca8a04', label: 'Medium' },
  high:   { color: '#dc2626', label: 'High' },
};

const BRANCH_PALETTE = [
  '#4a8bff', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316',
];

function BranchBadge({ label, idx, small }) {
  const color = BRANCH_PALETTE[idx % BRANCH_PALETTE.length];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: small ? '1px 6px' : '3px 10px',
        borderRadius: '999px',
        background: `${color}15`,
        color,
        fontSize: small ? '11px' : '12px',
        fontWeight: 600,
        border: `1px solid ${color}30`,
        whiteSpace: 'nowrap',
      }}
    >
      <Users size={small ? 10 : 12} />
      {label}
    </span>
  );
}

function VerdictBadge({ verdict, showIcon = true }) {
  const meta = VERDICT_META[verdict] || VERDICT_META.insufficient_evidence;
  const Icon = meta.icon;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: '6px',
        background: meta.bg,
        color: meta.color,
        fontSize: '11px',
        fontWeight: 600,
        border: `1px solid ${meta.color}25`,
      }}
    >
      {showIcon && <Icon size={12} />}
      {meta.label}
    </span>
  );
}

function SeverityDot({ severity }) {
  const meta = SEVERITY_META[severity] || SEVERITY_META.medium;
  return (
    <span
      title={`Severity: ${meta.label}`}
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: meta.color,
        flexShrink: 0,
      }}
    />
  );
}

export default function ComparisonCard({ data }) {
  const {
    executive_summary,
    recommendation,
    standards_table,
    findings_by_bidder,
    bidder_keys,
    problem_statement,
    standards_used,
    elapsed_ms,
    download_url,
  } = data;

  const [expandedBidder, setExpandedBidder] = useState(null);
  const [showMatrix, setShowMatrix] = useState(true);

  const winner = recommendation?.recommended_bidder;
  const runnerUp = recommendation?.runner_up;
  const recRationale = recommendation?.rationale;
  const scoreMargin = recommendation?.score_margin;

  return (
    <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header */}
      <div
        style={{
          padding: '14px 16px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <GitCompare size={16} color="var(--primary)" />
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
            Branch-Isolated Bid Comparison
          </span>
        </div>
        {problem_statement && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
            <strong>Tender / Problem:</strong> {problem_statement}
          </div>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {bidder_keys?.map((bk, i) => (
            <BranchBadge key={bk} label={bk} idx={i} />
          ))}
        </div>
        {elapsed_ms !== undefined && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
            <Clock size={10} />
            Completed in {(elapsed_ms / 1000).toFixed(1)}s
          </div>
        )}
      </div>

      {/* Recommendation */}
      {winner && (
        <div
          style={{
            padding: '14px 16px',
            background: 'rgba(74,139,255,0.06)',
            border: '1.5px solid rgba(74,139,255,0.25)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <Trophy size={16} color="var(--primary)" />
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--primary)' }}>
              Recommendation: {winner}
            </span>
          </div>
          {runnerUp && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
              Runner-up: {runnerUp}
              {scoreMargin !== undefined && ` · Margin: ${scoreMargin.toFixed(2)} pts`}
            </div>
          )}
          {recRationale && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {recRationale}
            </div>
          )}
        </div>
      )}

      {/* Executive Summary */}
      {executive_summary && (
        <div
          style={{
            padding: '12px 16px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            fontSize: 13,
            lineHeight: 1.6,
            color: 'var(--text-primary)',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
            Executive Summary
          </div>
          {executive_summary}
        </div>
      )}

      {/* Standards Compliance Matrix */}
      {standards_table?.length > 0 && (
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
          }}
        >
          <button
            onClick={() => setShowMatrix(v => !v)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 14px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--text-primary)',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={14} color="var(--primary)" />
              Standards Compliance Matrix ({standards_table.length})
            </span>
            {showMatrix ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showMatrix && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-surface)', borderTop: '1px solid var(--border)' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Standard</th>
                    {bidder_keys?.map((bk, i) => (
                      <th key={bk} style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, whiteSpace: 'nowrap' }}>
                        <BranchBadge label={bk} idx={i} small />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {standards_table.map((row, ri) => (
                    <tr key={ri} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                        <div style={{ fontWeight: 600 }}>{row.standard_id}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{row.description}</div>
                      </td>
                      {bidder_keys?.map((bk) => {
                        const pb = row.per_bidder?.[bk];
                        return (
                          <td key={bk} style={{ padding: '8px 12px', textAlign: 'center' }}>
                            {pb ? (
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                                <VerdictBadge verdict={pb.verdict} showIcon={false} />
                                <SeverityDot severity={pb.severity} />
                              </div>
                            ) : (
                              <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Per-Bidder Findings */}
      {findings_by_bidder && Object.keys(findings_by_bidder).length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {Object.entries(findings_by_bidder).map(([bk, findings], bki) => {
            const isOpen = expandedBidder === bk;
            return (
              <div
                key={bk}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  overflow: 'hidden',
                }}
              >
                <button
                  onClick={() => setExpandedBidder(isOpen ? null : bk)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <BranchBadge label={bk} idx={bki} small />
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
                      {findings.length} standard{findings.length !== 1 ? 's' : ''} evaluated
                    </span>
                  </span>
                  {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>

                {isOpen && (
                  <div style={{ padding: '0 14px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {findings.map((f, fi) => (
                      <div
                        key={fi}
                        style={{
                          padding: '10px 12px',
                          borderRadius: '8px',
                          background: 'var(--bg-surface)',
                          border: '1px solid var(--border)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                            {f.standard_id}
                          </span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <VerdictBadge verdict={f.verdict} />
                            <SeverityDot severity={f.severity} />
                          </div>
                        </div>
                        {f.rationale && (
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            {f.rationale}
                          </div>
                        )}
                        {f.citations?.length > 0 && (
                          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                            Citations: {f.citations.join(', ')}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Download */}
      {download_url && (
        <a
          href={download_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            padding: '10px 16px',
            background: 'var(--primary)',
            color: '#fff',
            borderRadius: 'var(--radius-md)',
            fontSize: 13,
            fontWeight: 600,
            textDecoration: 'none',
            alignSelf: 'flex-start',
          }}
        >
          <FileDown size={15} />
          Download Report (.docx)
        </a>
      )}
    </div>
  );
}
