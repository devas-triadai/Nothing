/**
 * AGRA Agent — Compliance Checker Page
 * Step-by-step compliance analysis with SSE streaming findings.
 */

import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, ShieldCheck, FileCheck, AlertTriangle, CheckCircle2,
  XCircle, HelpCircle, Loader2, Download, ChevronRight,
  Search, FileText,
} from 'lucide-react';
import api, { getApiUrl } from '../utils/api';
import { connectStream } from '../utils/stream';

const VERDICT_CONFIG = {
  Compliant:     { color: '#00c853', bg: 'rgba(0,200,83,0.10)',  icon: CheckCircle2,   label: 'Compliant' },
  'Non-Compliant': { color: '#ff4757', bg: 'rgba(255,71,87,0.10)', icon: XCircle,        label: 'Non-Compliant' },
  Partial:       { color: '#f0b429', bg: 'rgba(240,180,41,0.10)', icon: AlertTriangle,  label: 'Partial' },
  Missing:       { color: '#9333ea', bg: 'rgba(147,51,234,0.10)', icon: HelpCircle,     label: 'Missing Requirement' },
  Contradiction: { color: '#ef4444', bg: 'rgba(239,68,68,0.10)',  icon: AlertTriangle,  label: 'Contradiction' },
  Unverifiable:  { color: '#8899bb', bg: 'rgba(136,153,187,0.10)',icon: HelpCircle,     label: 'Unverifiable' },
};

export default function CompliancePage() {
  const [step, setStep] = useState(1);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  // Step 1 — subject documents
  const [subjectDocIds, setSubjectDocIds] = useState([]);
  // Step 2 — standard documents
  const [standardDocIds, setStandardDocIds] = useState([]);
  // Step 3 — results
  const [running, setRunning] = useState(false);
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [error, setError] = useState('');

  const findingsEndRef = useRef(null);

  useEffect(() => {
    api.get('/documents')
      .then(({ data }) => setDocuments(data.documents || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    findingsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [findings]);

  const toggleSubject = (docId) => {
    setSubjectDocIds(prev =>
      prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]
    );
  };

  const toggleStandard = (docId) => {
    setStandardDocIds(prev =>
      prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]
    );
  };

  const canProceed = () => {
    if (step === 1) return subjectDocIds.length > 0;
    if (step === 2) return standardDocIds.length > 0;
    return false;
  };

  const handleNext = () => {
    if (step < 3 && canProceed()) setStep(step + 1);
  };

  const runCheck = () => {
    setRunning(true);
    setFindings([]);
    setSummary(null);
    setDownloadUrl(null);
    setError('');

    connectStream(
      getApiUrl('/api/agent/compliance/check'),
      {
        subject_doc_ids: subjectDocIds,
        standard_doc_ids: standardDocIds,
      },
      // onToken — each finding
      (data) => {
        if (data.finding) {
          setFindings(prev => [...prev, data.finding]);
        }
      },
      // onDone
      (data) => {
        setRunning(false);
        if (data.download_url) setDownloadUrl(data.download_url);
        if (data.summary) setSummary(data.summary);
      },
      // onError
      (err) => {
        setRunning(false);
        setError(err.message);
      }
    );
  };

  const getSubjectNames = () => {
    const names = documents.filter(d => subjectDocIds.includes(d.doc_id)).map(d => d.filename);
    if (names.length === 0) return 'Documents';
    if (names.length === 1) return names[0];
    return `${names[0]} and ${names.length - 1} more`;
  };

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <Link to="/" style={styles.backLink}><ArrowLeft size={18} /></Link>
        <div>
          <h1 style={styles.title}>Compliance Checker</h1>
          <p style={styles.subtitle}>Analyse documents against regulatory standards</p>
        </div>
      </div>

      {/* Step Indicator */}
      <div style={styles.steps}>
        {[
          { n: 1, label: 'Select Subject' },
          { n: 2, label: 'Select Standards' },
          { n: 3, label: 'Run Analysis' },
        ].map(({ n, label }) => (
          <div
            key={n}
            style={{
              ...styles.stepItem,
              ...(step >= n ? styles.stepActive : {}),
              ...(step === n ? styles.stepCurrent : {}),
            }}
          >
            <div style={{
              ...styles.stepCircle,
              background: step >= n ? 'var(--primary)' : 'var(--border)',
              color: step >= n ? '#fff' : 'var(--text-muted)',
            }}>
              {n}
            </div>
            <span style={{ fontSize: '12px', fontWeight: step === n ? 600 : 400 }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div style={styles.card}>
        {/* Step 1 */}
        {step === 1 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}>
              <FileCheck size={20} />
              Select Subject Document(s)
            </h2>
            <p style={styles.stepDesc}>Choose the documents (e.g. shipbuilder bid, drawings) you want to evaluate.</p>
            <div style={styles.docGrid}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: '40px' }}>
                  <Loader2 size={24} style={{ animation: 'spin 1s linear infinite' }} color="var(--primary)" />
                </div>
              ) : documents.map(doc => (
                <div
                  key={doc.doc_id}
                  style={{
                    ...styles.docCard,
                    borderColor: subjectDocIds.includes(doc.doc_id) ? 'var(--primary)' : 'var(--border)',
                    background: subjectDocIds.includes(doc.doc_id) ? 'rgba(74,139,255,0.05)' : 'var(--bg-card)',
                  }}
                  onClick={() => toggleSubject(doc.doc_id)}
                >
                  <input
                    type="checkbox"
                    checked={subjectDocIds.includes(doc.doc_id)}
                    readOnly
                    style={{ accentColor: 'var(--primary)', width: 16, height: 16, cursor: 'pointer' }}
                  />
                  <div style={styles.docCardName}>{doc.filename}</div>
                  <div style={{ fontSize: '11px', color: doc.category === 'Global Standard' ? '#22c55e' : 'var(--accent-blue-light)', marginBottom: '4px', fontWeight: 600 }}>
                    {doc.category || 'Uncategorised'}
                  </div>
                  <div style={styles.docCardMeta}>{doc.chunks} chunks • {doc.page_count} pages</div>
                </div>
              ))}
            </div>
            <div style={styles.navRow}>
              <div />
              <button onClick={handleNext} disabled={!canProceed()} style={styles.nextBtn} id="step1-next">
                Next: Select Standards <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 2 */}
        {step === 2 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}>
              <ShieldCheck size={20} />
              Select Standard Documents
            </h2>
            <p style={styles.stepDesc}>
              Choose one or more standard/regulatory documents to check against. Selected subjects: <strong style={{ color: 'var(--primary)' }}>{getSubjectNames()}</strong>
            </p>
            <div style={styles.docGrid}>
              {documents
                .filter(d => !subjectDocIds.includes(d.doc_id))
                .map(doc => (
                  <div
                    key={doc.doc_id}
                    onClick={() => toggleStandard(doc.doc_id)}
                    style={{
                      ...styles.docCard,
                      borderColor: standardDocIds.includes(doc.doc_id) ? 'var(--primary)' : 'var(--border)',
                      background: standardDocIds.includes(doc.doc_id) ? 'var(--primary-dim)' : 'var(--bg-input)',
                    }}
                  >
                    <div style={{
                      width: 18,
                      height: 18,
                      borderRadius: '4px',
                      border: `2px solid ${standardDocIds.includes(doc.doc_id) ? 'var(--primary)' : 'var(--border)'}`,
                      background: standardDocIds.includes(doc.doc_id) ? 'var(--primary)' : 'transparent',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      {standardDocIds.includes(doc.doc_id) && <CheckCircle2 size={12} color="#fff" />}
                    </div>
                    <div style={styles.docCardName}>{doc.filename}</div>
                    <div style={{ fontSize: '11px', color: doc.category === 'Global Standard' ? '#22c55e' : 'var(--accent-blue-light)', marginBottom: '4px', fontWeight: 600 }}>
                      {doc.category || 'Uncategorised'}
                    </div>
                    <div style={styles.docCardMeta}>{doc.chunks} chunks</div>
                  </div>
                ))}
            </div>
            <div style={styles.navRow}>
              <button onClick={() => setStep(1)} style={styles.backBtn}>Back</button>
              <button onClick={handleNext} disabled={!canProceed()} style={styles.nextBtn} id="step2-next">
                Next: Run Analysis <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 3 */}
        {step === 3 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}>
              <Search size={20} />
              Compliance Analysis
            </h2>
            <p style={styles.stepDesc}>
              Checking <strong style={{ color: 'var(--primary)' }}>{getSubjectNames()}</strong> against {standardDocIds.length} standard document{standardDocIds.length !== 1 ? 's' : ''}.
            </p>

            {!running && findings.length === 0 && (
              <div style={{ textAlign: 'center', padding: '32px' }}>
                <button onClick={runCheck} style={styles.runBtn} id="run-compliance-btn">
                  <ShieldCheck size={18} />
                  Run Compliance Check
                </button>
              </div>
            )}

            {error && <div style={styles.errorMsg}>{error}</div>}

            {/* Summary */}
            {summary && (
              <div style={styles.summaryBar}>
                <div style={styles.summaryItem}>
                  <span style={{ color: '#00c853', fontWeight: 700, fontSize: '20px' }}>{summary.compliant}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Compliant</span>
                </div>
                <div style={styles.summaryItem}>
                  <span style={{ color: '#ff4757', fontWeight: 700, fontSize: '20px' }}>{summary.non_compliant}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Non-Compliant</span>
                </div>
                <div style={styles.summaryItem}>
                  <span style={{ color: '#f0b429', fontWeight: 700, fontSize: '20px' }}>{summary.partial}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Partial</span>
                </div>
                <div style={styles.summaryItem}>
                  <span style={{ color: '#9333ea', fontWeight: 700, fontSize: '20px' }}>{summary.missing || 0}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Missing</span>
                </div>
                <div style={styles.summaryItem}>
                  <span style={{ color: '#ef4444', fontWeight: 700, fontSize: '20px' }}>{summary.contradiction || 0}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Contradiction</span>
                </div>
                <div style={styles.summaryItem}>
                  <span style={{ color: '#8899bb', fontWeight: 700, fontSize: '20px' }}>{summary.unverifiable}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Unverifiable</span>
                </div>
              </div>
            )}

            {/* Findings Grouped by Topic */}
            <div style={styles.findingsList}>
              {Object.entries(
                findings.reduce((acc, f) => {
                  const t = f.topic || 'General Requirements';
                  if (!acc[t]) acc[t] = [];
                  acc[t].push(f);
                  return acc;
                }, {})
              ).map(([topic, tFindings]) => (
                <div key={topic} style={{ marginBottom: '24px' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px', paddingBottom: '8px', borderBottom: '1px solid var(--border)' }}>
                    {topic}
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {tFindings.map((f, i) => {
                      const v = VERDICT_CONFIG[f.verdict] || VERDICT_CONFIG.Unverifiable;
                      const VIcon = v.icon;
                      return (
                        <div key={i} style={{ ...styles.findingCard, borderLeftColor: v.color }} className="animate-slide-up">
                          <div style={styles.findingHeader}>
                            <div style={{ ...styles.verdictBadge, background: v.bg, color: v.color }}>
                              <VIcon size={14} />
                              {v.label}
                            </div>
                            <span style={styles.findingClause}>{f.clause}</span>
                          </div>
                          <div style={styles.findingBody}>
                            <div style={styles.fieldGroup}>
                              <div style={styles.fieldLabel}>Requirement</div>
                              <div style={styles.fieldValue}>{f.requirement}</div>
                            </div>
                            <div style={styles.fieldGroup}>
                              <div style={styles.fieldLabel}>Finding</div>
                              <div style={styles.fieldValue}>{f.finding}</div>
                            </div>
                            {f.recommendation && (
                              <div style={styles.fieldGroup}>
                                <div style={styles.fieldLabel}>Recommendation</div>
                                <div style={{ ...styles.fieldValue, color: 'var(--accent-amber)' }}>{f.recommendation}</div>
                              </div>
                            )}
                            {f.citation && (
                              <div style={styles.fieldGroup}>
                                <div style={styles.fieldLabel}>Citation</div>
                                <div style={{
                                  ...styles.fieldValue,
                                  fontStyle: 'italic',
                                  background: 'rgba(74,139,255,0.05)',
                                  padding: '8px 10px',
                                  borderRadius: '6px',
                                  borderLeft: '2px solid var(--primary)',
                                }}>{f.citation}</div>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
              {running && (
                <div style={{ textAlign: 'center', padding: '24px' }}>
                  <Loader2 size={24} style={{ animation: 'spin 1s linear infinite' }} color="var(--primary)" />
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '8px' }}>
                    Analysing clauses...
                  </div>
                </div>
              )}
              <div ref={findingsEndRef} />
            </div>

            {/* Download Report */}
            {downloadUrl && !running && (
              <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <a href={downloadUrl} style={styles.downloadReportBtn} target="_blank" rel="noopener">
                  <Download size={18} />
                  Download Compliance Report (.docx)
                </a>
              </div>
            )}

            <div style={styles.navRow}>
              <button onClick={() => setStep(2)} style={styles.backBtn}>Back</button>
              {findings.length > 0 && !running && (
                <button
                  onClick={() => { setFindings([]); setSummary(null); setDownloadUrl(null); runCheck(); }}
                  style={styles.rerunBtn}
                >
                  Re-run Analysis
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  page: {
    padding: '28px 32px',
    maxWidth: '960px',
    margin: '0 auto',
    minHeight: '100vh',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    marginBottom: '24px',
  },
  backLink: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 38,
    height: 38,
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
    textDecoration: 'none',
    flexShrink: 0,
  },
  title: {
    fontSize: '22px',
    fontWeight: 700,
    color: 'var(--text-heading)',
    margin: 0,
  },
  subtitle: {
    fontSize: '13px',
    color: 'var(--text-muted)',
    margin: 0,
  },

  /* Steps */
  steps: {
    display: 'flex',
    gap: '4px',
    marginBottom: '24px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 16px',
  },
  stepItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flex: 1,
    color: 'var(--text-muted)',
    padding: '6px 0',
  },
  stepActive: {
    color: 'var(--text-primary)',
  },
  stepCurrent: {
    color: 'var(--primary)',
  },
  stepCircle: {
    width: 26,
    height: 26,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    fontSize: '12px',
    fontWeight: 700,
    flexShrink: 0,
  },

  /* Card */
  card: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '24px',
    boxShadow: 'var(--shadow-md)',
  },
  stepTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    fontSize: '18px',
    fontWeight: 700,
    color: 'var(--text-heading)',
    marginBottom: '8px',
  },
  stepDesc: {
    fontSize: '13px',
    color: 'var(--text-secondary)',
    marginBottom: '20px',
    lineHeight: '1.6',
  },

  /* Document Cards */
  docGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
    gap: '10px',
    marginBottom: '20px',
  },
  docCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    padding: '14px',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    transition: 'border-color 0.15s, background 0.15s',
  },
  docCardName: {
    fontSize: '13px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  docCardMeta: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },

  /* Nav */
  navRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: '16px',
    borderTop: '1px solid var(--border)',
    marginTop: '8px',
  },
  nextBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '10px 20px',
    background: 'var(--primary)',
    color: '#fff',
    borderRadius: 'var(--radius-md)',
    fontSize: '13px',
    fontWeight: 600,
    border: 'none',
  },
  backBtn: {
    padding: '10px 20px',
    background: 'transparent',
    color: 'var(--text-secondary)',
    borderRadius: 'var(--radius-md)',
    fontSize: '13px',
    fontWeight: 500,
    border: '1px solid var(--border)',
  },
  runBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 32px',
    background: 'linear-gradient(135deg, #4a8bff, #3a6fd8)',
    color: '#fff',
    borderRadius: 'var(--radius-lg)',
    fontSize: '15px',
    fontWeight: 700,
    border: 'none',
    boxShadow: '0 4px 20px rgba(74, 139, 255, 0.3)',
  },
  rerunBtn: {
    padding: '10px 20px',
    background: 'rgba(74, 139, 255, 0.1)',
    color: 'var(--primary)',
    borderRadius: 'var(--radius-md)',
    fontSize: '13px',
    fontWeight: 600,
    border: '1px solid rgba(74, 139, 255, 0.25)',
  },

  /* Findings */
  findingsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    marginTop: '16px',
  },
  findingCard: {
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderLeft: '4px solid',
    borderRadius: 'var(--radius-md)',
    overflow: 'hidden',
  },
  findingHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px 16px',
    background: 'rgba(0,0,0,0.15)',
    borderBottom: '1px solid var(--border)',
  },
  verdictBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '4px 12px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: 700,
  },
  findingClause: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  findingBody: {
    padding: '14px 16px',
  },
  fieldGroup: {
    marginBottom: '10px',
  },
  fieldLabel: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
    marginBottom: '3px',
  },
  fieldValue: {
    fontSize: '13px',
    color: 'var(--text-secondary)',
    lineHeight: '1.6',
  },

  /* Summary */
  summaryBar: {
    display: 'flex',
    gap: '16px',
    padding: '16px',
    background: 'var(--bg-surface)',
    borderRadius: 'var(--radius-md)',
    marginBottom: '16px',
    justifyContent: 'center',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '2px',
    minWidth: '80px',
  },

  downloadReportBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 32px',
    background: 'linear-gradient(135deg, #00c853, #00a843)',
    color: '#fff',
    borderRadius: 'var(--radius-lg)',
    fontSize: '14px',
    fontWeight: 700,
    textDecoration: 'none',
    boxShadow: '0 4px 20px rgba(0, 200, 83, 0.25)',
  },

  errorMsg: {
    padding: '10px 14px',
    background: 'rgba(255, 71, 87, 0.1)',
    border: '1px solid rgba(255, 71, 87, 0.25)',
    borderRadius: 'var(--radius-md)',
    color: '#ff4757',
    fontSize: '13px',
    marginBottom: '16px',
  },
};
