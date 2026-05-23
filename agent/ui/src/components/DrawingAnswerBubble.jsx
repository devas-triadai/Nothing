/**
 * AGRA Chat Enhancement Phase 5 — Drawing Answer Bubble
 * Displays drawing analysis results with confidence and suggestions.
 */

import { useState } from 'react';
import { 
  FileImage, ChevronDown, ChevronUp, ExternalLink, 
  AlertTriangle, CheckCircle, Info, Lightbulb, Shield
} from 'lucide-react';
import { renderMarkdown } from '../utils/markdown';

export default function DrawingAnswerBubble({ 
  answer, 
  drawingSummary, 
  ragSources, 
  confidence, 
  suggestions,
  isDark = false 
}) {
  const [showSources, setShowSources] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);

  const getConfidenceColor = (score) => {
    if (score >= 0.80) return '#22c55e'; // Green
    if (score >= 0.60) return '#eab308'; // Yellow
    return '#ef4444'; // Red
  };

  const getSuggestionIcon = (type) => {
    switch (type) {
      case 'vessel_match': return <CheckCircle size={14} color="#22c55e" />;
      case 'upgrade': return <Lightbulb size={14} color="#3b82f6" />;
      case 'advancement': return <Info size={14} color="#8b5cf6" />;
      case 'gap_analysis': return <AlertTriangle size={14} color="#ef4444" />;
      case 'compliance': return <Shield size={14} color="#06b6d4" />;
      default: return <Info size={14} color="#64748b" />;
    }
  };

  const getSuggestionColor = (type) => {
    switch (type) {
      case 'vessel_match': return isDark ? 'rgba(34, 197, 94, 0.2)' : 'rgba(34, 197, 94, 0.1)';
      case 'upgrade': return isDark ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.1)';
      case 'advancement': return isDark ? 'rgba(139, 92, 246, 0.2)' : 'rgba(139, 92, 246, 0.1)';
      case 'gap_analysis': return isDark ? 'rgba(239, 68, 68, 0.2)' : 'rgba(239, 68, 68, 0.1)';
      case 'compliance': return isDark ? 'rgba(6, 182, 212, 0.2)' : 'rgba(6, 182, 212, 0.1)';
      default: return isDark ? 'rgba(100, 116, 139, 0.2)' : 'rgba(100, 116, 139, 0.1)';
    }
  };

  const styles = {
    container: {
      background: isDark ? 'rgba(30, 41, 59, 0.8)' : 'rgba(255, 255, 255, 0.95)',
      borderRadius: '16px',
      padding: '16px',
      border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
      maxWidth: '100%',
      animation: 'fadeIn 0.3s ease-out forwards',
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      marginBottom: '12px',
    },
    icon: {
      padding: '8px',
      background: isDark ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.1)',
      borderRadius: '8px',
    },
    title: {
      fontSize: '14px',
      fontWeight: 600,
      color: isDark ? '#e2e8f0' : '#1e293b',
    },
    answer: {
      fontSize: '14px',
      lineHeight: '1.6',
      color: isDark ? '#cbd5e1' : '#334155',
      marginBottom: '16px',
    },
    confidenceSection: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '10px 14px',
      background: isDark ? 'rgba(15, 23, 42, 0.6)' : 'rgba(241, 245, 249, 0.8)',
      borderRadius: '10px',
      marginBottom: '12px',
    },
    confidenceScore: {
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      fontSize: '13px',
      fontWeight: 600,
    },
    confidenceBar: {
      flex: 1,
      height: '6px',
      background: isDark ? '#334155' : '#e2e8f0',
      borderRadius: '3px',
      overflow: 'hidden',
    },
    confidenceFill: {
      height: '100%',
      borderRadius: '3px',
      transition: 'width 0.3s ease',
    },
    confidenceDetails: {
      display: 'flex',
      gap: '12px',
      fontSize: '11px',
      color: isDark ? '#64748b' : '#94a3b8',
    },
    summaryGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: '8px',
      marginBottom: '12px',
    },
    summaryItem: {
      padding: '8px 12px',
      background: isDark ? 'rgba(15, 23, 42, 0.4)' : 'rgba(241, 245, 249, 0.6)',
      borderRadius: '8px',
      fontSize: '12px',
    },
    summaryLabel: {
      color: isDark ? '#64748b' : '#94a3b8',
      marginBottom: '2px',
    },
    summaryValue: {
      color: isDark ? '#e2e8f0' : '#1e293b',
      fontWeight: 500,
    },
    section: {
      marginTop: '12px',
      borderTop: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
      paddingTop: '12px',
    },
    sectionHeader: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      cursor: 'pointer',
      marginBottom: '8px',
    },
    sectionTitle: {
      fontSize: '13px',
      fontWeight: 600,
      color: isDark ? '#94a3b8' : '#64748b',
    },
    suggestion: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '10px',
      padding: '10px 12px',
      borderRadius: '8px',
      marginBottom: '8px',
      fontSize: '13px',
      animation: 'staggerIn 0.3s ease-out forwards',
      opacity: 0,
    },
    suggestionText: {
      flex: 1,
      color: isDark ? '#e2e8f0' : '#1e293b',
      lineHeight: '1.4',
    },
    suggestionConfidence: {
      fontSize: '11px',
      color: isDark ? '#64748b' : '#94a3b8',
      marginTop: '4px',
    },
    source: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      padding: '8px 12px',
      background: isDark ? 'rgba(15, 23, 42, 0.4)' : 'rgba(241, 245, 249, 0.6)',
      borderRadius: '8px',
      marginBottom: '6px',
      fontSize: '12px',
    },
    sourceName: {
      flex: 1,
      color: isDark ? '#e2e8f0' : '#1e293b',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
    },
    sourceScore: {
      fontSize: '11px',
      padding: '2px 6px',
      background: isDark ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.1)',
      borderRadius: '4px',
      color: '#3b82f6',
    },
  };

  const answerHtml = renderMarkdown(answer || '');

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.icon}>
          <FileImage size={18} color="#3b82f6" />
        </div>
        <span style={styles.title}>Drawing Analysis Results</span>
      </div>

      {/* Answer */}
      <div 
        style={styles.answer}
        dangerouslySetInnerHTML={{ __html: answerHtml }}
      />

      {/* Confidence Display */}
      {confidence && (
        <div style={styles.confidenceSection}>
          <div style={styles.confidenceScore}>
            <span style={{ color: getConfidenceColor(confidence.overall) }}>
              {Math.round(confidence.overall * 100)}%
            </span>
            <span style={{ color: isDark ? '#64748b' : '#94a3b8' }}>confidence</span>
          </div>
          <div style={styles.confidenceBar}>
            <div 
              style={{
                ...styles.confidenceFill,
                width: `${confidence.overall * 100}%`,
                background: getConfidenceColor(confidence.overall),
              }}
            />
          </div>
        </div>
      )}

      {/* Drawing Summary */}
      {drawingSummary && (
        <div style={styles.summaryGrid}>
          {drawingSummary.vessel_name && (
            <div style={styles.summaryItem}>
              <div style={styles.summaryLabel}>Vessel</div>
              <div style={styles.summaryValue}>{drawingSummary.vessel_name}</div>
            </div>
          )}
          {drawingSummary.drawing_type && (
            <div style={styles.summaryItem}>
              <div style={styles.summaryLabel}>Type</div>
              <div style={styles.summaryValue}>
                {drawingSummary.drawing_type.replace(/_/g, ' ')}
              </div>
            </div>
          )}
          {drawingSummary.dimensions_count !== undefined && (
            <div style={styles.summaryItem}>
              <div style={styles.summaryLabel}>Dimensions</div>
              <div style={styles.summaryValue}>{drawingSummary.dimensions_count} found</div>
            </div>
          )}
          {drawingSummary.equipment_count !== undefined && (
            <div style={styles.summaryItem}>
              <div style={styles.summaryLabel}>Equipment</div>
              <div style={styles.summaryValue}>{drawingSummary.equipment_count} items</div>
            </div>
          )}
        </div>
      )}

      {/* Suggestions */}
      {suggestions && suggestions.length > 0 && (
        <div style={styles.section}>
          <div 
            style={styles.sectionHeader}
            onClick={() => setShowSuggestions(!showSuggestions)}
          >
            <span style={styles.sectionTitle}>
              💡 Suggestions ({suggestions.length})
            </span>
            {showSuggestions ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          
          {showSuggestions && (
            <div>
              {suggestions.map((sug, idx) => (
                <div 
                  key={idx}
                  style={{
                    ...styles.suggestion,
                    background: getSuggestionColor(sug.type),
                    animationDelay: `${idx * 0.1}s`,
                  }}
                >
                  {getSuggestionIcon(sug.type)}
                  <div style={styles.suggestionText}>
                    {sug.text}
                    <div style={styles.suggestionConfidence}>
                      Confidence: {Math.round(sug.confidence * 100)}%
                      {sug.action && ` • Action: ${sug.action}`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* RAG Sources */}
      {ragSources && ragSources.length > 0 && (
        <div style={styles.section}>
          <div 
            style={styles.sectionHeader}
            onClick={() => setShowSources(!showSources)}
          >
            <span style={styles.sectionTitle}>
              📚 Sources ({ragSources.length})
            </span>
            {showSources ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
          
          {showSources && (
            <div>
              {ragSources.map((src, idx) => (
                <div key={idx} style={styles.source}>
                  <ExternalLink size={12} color="#64748b" />
                  <span style={styles.sourceName} title={src.excerpt}>
                    {src.document_name}
                  </span>
                  <span style={styles.sourceScore}>
                    {Math.round(src.relevance_score * 100)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
