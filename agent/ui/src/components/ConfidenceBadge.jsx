import React from 'react';
import { Shield, AlertTriangle, CheckCircle, Info } from 'lucide-react';

/**
 * ConfidenceBadge - Displays RAG response confidence and quality metrics
 * 
 * Shows:
 * - Confidence level (High/Medium/Low) with color coding
 * - Citation accuracy percentage
 * - Hallucination rate warning if high
 * - Detailed breakdown on hover
 */

const ConfidenceBadge = ({ 
  confidenceScore, 
  citationAccuracy, 
  hallucinationRate,
  chunksUsed,
  responseTimeMs 
}) => {
  // Determine confidence level
  let level = 'low';
  let color = '#d50000';  // Red
  let icon = AlertTriangle;
  let label = 'Low Confidence';
  
  if (confidenceScore >= 0.7) {
    level = 'high';
    color = '#00c853';  // Green
    icon = CheckCircle;
    label = 'High Confidence';
  } else if (confidenceScore >= 0.4) {
    level = 'medium';
    color = '#f0b429';  // Yellow
    icon = Shield;
    label = 'Medium Confidence';
  }
  
  const Icon = icon;
  
  // Hallucination warning threshold (> 20% is concerning)
  const showHallucinationWarning = hallucinationRate > 20;
  
  // Citation accuracy check (< 90% is concerning)
  const showCitationWarning = citationAccuracy < 90;
  
  return (
    <div style={styles.container}>
      {/* Main confidence badge */}
      <div 
        style={{
          ...styles.badge,
          backgroundColor: `${color}15`,
          borderColor: color,
          color: color,
        }}
        title={`Confidence: ${(confidenceScore * 100).toFixed(1)}%`}
      >
        <Icon size={14} style={styles.icon} />
        <span style={styles.label}>{label}</span>
      </div>
      
      {/* Warning badges */}
      {showHallucinationWarning && (
        <div 
          style={{...styles.warningBadge, backgroundColor: '#d5000015', color: '#d50000'}}
          title={`${hallucinationRate.toFixed(1)}% of claims may be unsupported`}
        >
          <AlertTriangle size={12} style={styles.icon} />
          <span>Hallucination Risk</span>
        </div>
      )}
      
      {showCitationWarning && !showHallucinationWarning && (
        <div 
          style={{...styles.warningBadge, backgroundColor: '#ff6d0015', color: '#ff6d00'}}
          title={`${citationAccuracy.toFixed(1)}% citation accuracy`}
        >
          <Info size={12} style={styles.icon} />
          <span>Citation Issues</span>
        </div>
      )}
      
      {/* Detailed stats tooltip area */}
      <div style={styles.details}>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Confidence:</span>
          <span style={styles.detailValue}>{(confidenceScore * 100).toFixed(1)}%</span>
        </div>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Citation Accuracy:</span>
          <span style={{...styles.detailValue, color: citationAccuracy >= 90 ? '#00c853' : '#f0b429'}}>
            {citationAccuracy?.toFixed(1) || 'N/A'}%
          </span>
        </div>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Hallucination Rate:</span>
          <span style={{...styles.detailValue, color: hallucinationRate < 10 ? '#00c853' : '#d50000'}}>
            {hallucinationRate?.toFixed(1) || 'N/A'}%
          </span>
        </div>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Sources Used:</span>
          <span style={styles.detailValue}>{chunksUsed || 'N/A'}</span>
        </div>
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Response Time:</span>
          <span style={styles.detailValue}>{responseTimeMs ? `${responseTimeMs.toFixed(0)}ms` : 'N/A'}</span>
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    marginTop: '12px',
    padding: '10px 12px',
    backgroundColor: 'var(--surface, #f8fafc)',
    borderRadius: '8px',
    border: '1px solid var(--border, #e2e8f0)',
    fontSize: '12px',
  },
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: '12px',
    border: '1px solid',
    fontWeight: '600',
    fontSize: '11px',
    width: 'fit-content',
  },
  warningBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: '10px',
    fontWeight: '500',
    fontSize: '10px',
    width: 'fit-content',
  },
  icon: {
    flexShrink: 0,
  },
  label: {
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  details: {
    display: 'grid',
    gridTemplateColumns: '1fr auto',
    gap: '4px 12px',
    marginTop: '4px',
    paddingTop: '8px',
    borderTop: '1px dashed var(--border, #e2e8f0)',
  },
  detailRow: {
    display: 'contents',
  },
  detailLabel: {
    color: 'var(--text-muted, #64748b)',
  },
  detailValue: {
    fontWeight: '600',
    color: 'var(--text-primary, #1e293b)',
    textAlign: 'right',
  },
};

export default ConfidenceBadge;
