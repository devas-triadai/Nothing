/**
 * AGRA Chat Enhancement Phase 5 — Confidence Panel
 * Detailed confidence breakdown display with visual bars.
 */

import { useState } from 'react';
import { ChevronDown, ChevronUp, Activity } from 'lucide-react';

export default function ConfidencePanel({ confidence, isDark = false, compact = false }) {
  const [expanded, setExpanded] = useState(!compact);

  if (!confidence) return null;

  const getColor = (score) => {
    if (score >= 0.80) return '#22c55e';
    if (score >= 0.60) return '#eab308';
    return '#ef4444';
  };

  const getLabel = (score) => {
    if (score >= 0.80) return 'High';
    if (score >= 0.60) return 'Medium';
    return 'Low';
  };

  const factors = [
    { key: 'vlm', label: 'VLM Analysis', value: confidence.vlm },
    { key: 'ocr', label: 'OCR Extraction', value: confidence.ocr },
    { key: 'rag', label: 'Database Match', value: confidence.rag },
    { key: 'query_clarity', label: 'Query Clarity', value: confidence.query_clarity },
  ];

  const styles = {
    container: {
      background: isDark ? 'rgba(15, 23, 42, 0.6)' : 'rgba(241, 245, 249, 0.8)',
      borderRadius: '10px',
      padding: compact ? '10px 14px' : '14px',
      border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      cursor: compact ? 'pointer' : 'default',
    },
    headerLeft: {
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
    },
    icon: {
      color: getColor(confidence.overall),
    },
    title: {
      fontSize: '13px',
      fontWeight: 600,
      color: isDark ? '#e2e8f0' : '#1e293b',
    },
    overallBadge: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
    },
    score: {
      fontSize: '18px',
      fontWeight: 700,
      color: getColor(confidence.overall),
    },
    label: {
      fontSize: '11px',
      padding: '3px 8px',
      background: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)',
      borderRadius: '4px',
      color: isDark ? '#94a3b8' : '#64748b',
    },
    expandButton: {
      background: 'none',
      border: 'none',
      padding: '4px',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      color: isDark ? '#64748b' : '#94a3b8',
    },
    factors: {
      marginTop: '12px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    },
    factor: {
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
    },
    factorHeader: {
      display: 'flex',
      justifyContent: 'space-between',
      fontSize: '12px',
    },
    factorLabel: {
      color: isDark ? '#94a3b8' : '#64748b',
    },
    factorValue: {
      fontWeight: 500,
      color: isDark ? '#e2e8f0' : '#1e293b',
    },
    barBg: {
      height: '6px',
      background: isDark ? '#334155' : '#e2e8f0',
      borderRadius: '3px',
      overflow: 'hidden',
    },
    barFill: {
      height: '100%',
      borderRadius: '3px',
      transition: 'width 0.3s ease',
      animation: 'confidenceGrow 0.6s ease-out forwards',
    },
  };

  return (
    <div style={styles.container}>
      <div 
        style={styles.header}
        onClick={() => compact && setExpanded(!expanded)}
      >
        <div style={styles.headerLeft}>
          <Activity size={18} style={styles.icon} />
          <span style={styles.title}>
            {compact ? 'Analysis Confidence' : 'Confidence Breakdown'}
          </span>
        </div>
        
        <div style={styles.overallBadge}>
          <span style={styles.score}>{Math.round(confidence.overall * 100)}%</span>
          <span style={styles.label}>{getLabel(confidence.overall)}</span>
          {compact && (
            <button style={styles.expandButton}>
              {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div style={styles.factors}>
          {factors.map((factor) => (
            <div key={factor.key} style={styles.factor}>
              <div style={styles.factorHeader}>
                <span style={styles.factorLabel}>{factor.label}</span>
                <span style={styles.factorValue}>
                  {Math.round(factor.value * 100)}%
                </span>
              </div>
              <div style={styles.barBg}>
                <div
                  style={{
                    ...styles.barFill,
                    width: `${factor.value * 100}%`,
                    background: getColor(factor.value),
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
