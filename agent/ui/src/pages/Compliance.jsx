/**
 * AGRA Agent — Compliance Checker Page (v2)
 * Rebuilt: plain api.post() (no SSE), smart Step 2 standard recommendations,
 * running state always resets on success and error.
 */

import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, ShieldCheck, FileCheck, AlertTriangle, CheckCircle2,
  XCircle, HelpCircle, Loader2, Download, ChevronRight,
  Search, Upload, Star, Clock,
} from 'lucide-react';
import api, { getApiUrl } from '../utils/api';

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

  // Step 1
  const [subjectDocIds, setSubjectDocIds] = useState([]);

  // Step 2 — standards + recommendations
  const [standardDocIds, setStandardDocIds] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [recLoading, setRecLoading] = useState(false);

  // Step 3 — results
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [error, setError] = useState('');

  const elapsedRef = useRef(null);
  const fileInputRef = useRef(null);

  // Inline upload state
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

  const refreshDocuments = async () => {
    try {
      const { data } = await api.get('/documents');
      setDocuments(data.documents || []);
    } catch (err) {
      console.error('Failed to refresh documents', err);
    }
  };

  useEffect(() => {
    refreshDocuments().finally(() => setLoading(false));
  }, []);

  const isStandard = (doc) => {
    if (!doc) return false;
    const cat = (doc.category || '').toLowerCase();
    const dtype = (doc.document_type || '').toLowerCase();
    return doc.doc_id?.startsWith('builtin:') ||
      dtype === 'standard' ||
      cat.includes('standard') || cat.includes('sotr') ||
      cat.includes('imo') || cat.includes('rule');
  };

  const subjectDocs = documents.filter(d => !isStandard(d));
  const standardDocs = documents.filter(d => isStandard(d));

  const getSubjectNames = () => {
    const names = documents.filter(d => subjectDocIds.includes(d.doc_id)).map(d => d.filename);
    if (names.length === 0) return 'Documents';
    if (names.length === 1) return names[0];
    return `${names[0]} and ${names.length - 1} more`;
  };

  const toggleSubject = (docId) =>
    setSubjectDocIds(prev => prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]);

  const toggleStandard = (docId) =>
    setStandardDocIds(prev => prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]);

  const canProceed = () => {
    if (step === 1) return subjectDocIds.length > 0;
    if (step === 2) return standardDocIds.length > 0;
    return false;
  };

  // When moving to Step 2: fetch recommendations for selected subject docs
  const handleNext = async () => {
    if (step === 1 && canProceed()) {
      setStep(2);
      setRecLoading(true);
      setRecommendations([]);
      setStandardDocIds([]);
      try {
        const { data } = await api.post('/compliance/recommend-standards', {
          subject_doc_id: subjectDocIds[0],
        });
        const recs = data.recommendations || [];
        setRecommendations(recs);
        // Pre-tick recommended standards
        const autoSelected = recs.filter(r => r.recommended).map(r => r.doc_id);
        setStandardDocIds(autoSelected);
      } catch (err) {
        console.error('Recommendation fetch failed, showing all standards', err);
        // Fallback: show all standards unselected
        setRecommendations(
          standardDocs.map(d => ({ doc_id: d.doc_id, filename: d.filename, score: 0, recommended: false, reason: '' }))
        );
      } finally {
        setRecLoading(false);
      }
    } else if (step === 2 && canProceed()) {
      setStep(3);
    }
  };

  // Run compliance check — plain api.post(), always resets running
  const runCheck = async () => {
    setRunning(true);
    setFindings([]);
    setSummary(null);
    setDownloadUrl(null);
    setError('');
    setElapsed(0);

    // Elapsed time counter
    const startTime = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const { data } = await api.post('/compliance/check', {
        subject_doc_ids: subjectDocIds,
        standard_doc_ids: standardDocIds,
      });
      setFindings(data.findings || []);
      setSummary(data.summary || null);
      if (data.download_url) setDownloadUrl(data.download_url);
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || 'Compliance check failed.';
      setError(msg);
    } finally {
      clearInterval(elapsedRef.current);
      setRunning(false);
    }
  };

  const handleInlineUpload = async (file, categoryHint) => {
    setUploading(true);
    setUploadError('');
    try {
      const token = localStorage.getItem('agra_token') || '';
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', categoryHint === 'standard' ? 'standard' : 'bid');
      formData.append('auto_extract', 'true');

      const res = await fetch(getApiUrl('/api/agent/upload'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let newDocId = null;
      while (true) {
        const { value, done } = await reader.read();
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6).trim());
                if (evt.stage === 'done') newDocId = evt.doc_id;
                if (evt.stage === 'error') throw new Error(evt.error || 'Upload error');
              } catch (e) {
                if (!(e instanceof SyntaxError)) throw e;
              }
            }
          }
        }
        if (done) break;
      }
      const { data } = await api.get('/documents');
      const freshDocs = data.documents || [];
      setDocuments(freshDocs);
      const newDoc = freshDocs.find(d => d.doc_id === newDocId || d.filename === file.name);
      if (newDoc) {
        if (categoryHint === 'standard' || isStandard(newDoc)) {
          setStandardDocIds(prev => prev.includes(newDoc.doc_id) ? prev : [...prev, newDoc.doc_id]);
        } else {
          setSubjectDocIds(prev => prev.includes(newDoc.doc_id) ? prev : [...prev, newDoc.doc_id]);
        }
      }
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Build the Step 2 display list — merge recommendations with full standardDocs list
  const buildStep2List = () => {
    if (recLoading) return { recommended: [], additional: [] };
    if (recommendations.length === 0) {
      return {
        recommended: [],
        additional: standardDocs.filter(d => !subjectDocIds.includes(d.doc_id)).map(d => ({
          doc_id: d.doc_id, filename: d.filename, score: 0, recommended: false, reason: '',
          chunks: d.chunks, category: d.category,
        })),
      };
    }
    const recMap = new Map(recommendations.map(r => [r.doc_id, r]));
    // Include docs not in recommendations list (newly uploaded after rec fetch)
    const allStdIds = new Set(standardDocs.map(d => d.doc_id));
    const recIds = new Set(recommendations.map(r => r.doc_id));

    const recList = recommendations
      .filter(r => r.recommended && !subjectDocIds.includes(r.doc_id))
      .map(r => ({ ...r, ...documents.find(d => d.doc_id === r.doc_id) || {} }));

    const addList = [
      ...recommendations
        .filter(r => !r.recommended && !subjectDocIds.includes(r.doc_id))
        .map(r => ({ ...r, ...documents.find(d => d.doc_id === r.doc_id) || {} })),
      // newly uploaded standards not yet in recommendations
      ...standardDocs.filter(d => !recIds.has(d.doc_id) && !subjectDocIds.includes(d.doc_id))
        .map(d => ({ doc_id: d.doc_id, filename: d.filename, score: 0, recommended: false, reason: '', chunks: d.chunks, category: d.category })),
    ];

    return { recommended: recList, additional: addList };
  };

  const { recommended: recDocs, additional: addDocs } = buildStep2List();

  const renderStandardCard = (item) => {
    const selected = standardDocIds.includes(item.doc_id);
    return (
      <div
        key={item.doc_id}
        onClick={() => toggleStandard(item.doc_id)}
        style={{
          ...styles.docCard,
          borderColor: selected ? 'var(--primary)' : 'var(--border)',
          background: selected ? 'rgba(74,139,255,0.06)' : 'var(--bg-input)',
          position: 'relative',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <div style={{
            width: 16, height: 16, borderRadius: '3px', flexShrink: 0,
            border: `2px solid ${selected ? 'var(--primary)' : 'var(--border)'}`,
            background: selected ? 'var(--primary)' : 'transparent',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {selected && <CheckCircle2 size={10} color="#fff" />}
          </div>
          {item.recommended && (
            <span style={styles.recBadge}><Star size={9} /> Recommended</span>
          )}
        </div>
        <div style={styles.docCardName}>{item.filename}</div>
        <div style={{ fontSize: '11px', color: 'var(--accent-blue-light)', fontWeight: 600, marginBottom: 2 }}>
          {item.category || 'Standard'}
        </div>
        {item.score > 0 && (
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: 2 }}>
            Relevance: {Math.round(item.score * 100)}%
          </div>
        )}
        {item.reason && (
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', lineHeight: 1.4, marginTop: 2 }}>
            {item.reason}
          </div>
        )}
      </div>
    );
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
          <div key={n} style={{ ...styles.stepItem, ...(step >= n ? styles.stepActive : {}), ...(step === n ? styles.stepCurrent : {}) }}>
            <div style={{
              ...styles.stepCircle,
              background: step >= n ? 'var(--primary)' : 'var(--border)',
              color: step >= n ? '#fff' : 'var(--text-muted)',
            }}>{n}</div>
            <span style={{ fontSize: '12px', fontWeight: step === n ? 600 : 400 }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div style={styles.card}>

        {/* ── Step 1 ── */}
        {step === 1 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}><FileCheck size={20} />Select Subject Document(s)</h2>
            <p style={styles.stepDesc}>Choose the documents (e.g. shipbuilder bid, drawings) to evaluate.</p>
            <div style={styles.docGrid}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: '40px', gridColumn: '1 / -1' }}>
                  <Loader2 size={24} style={{ animation: 'spin 1s linear infinite' }} color="var(--primary)" />
                </div>
              ) : subjectDocs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', gridColumn: '1 / -1' }}>
                  No uploaded documents available. Please upload documents first.
                </div>
              ) : subjectDocs.map(doc => (
                <div
                  key={doc.doc_id}
                  style={{
                    ...styles.docCard,
                    borderColor: subjectDocIds.includes(doc.doc_id) ? 'var(--primary)' : 'var(--border)',
                    background: subjectDocIds.includes(doc.doc_id) ? 'rgba(74,139,255,0.05)' : 'var(--bg-card)',
                  }}
                  onClick={() => toggleSubject(doc.doc_id)}
                >
                  <input type="checkbox" checked={subjectDocIds.includes(doc.doc_id)} readOnly
                    style={{ accentColor: 'var(--primary)', width: 16, height: 16, cursor: 'pointer' }} />
                  <div style={styles.docCardName}>{doc.filename}</div>
                  <div style={{ fontSize: '11px', color: 'var(--accent-blue-light)', marginBottom: '4px', fontWeight: 600 }}>
                    {doc.category || 'Uncategorised'}
                  </div>
                  <div style={styles.docCardMeta}>{doc.chunks} chunks • {doc.page_count} pages</div>
                </div>
              ))}
              <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx,.txt" style={{ display: 'none' }}
                onChange={e => { const f = e.target.files?.[0]; if (f) handleInlineUpload(f, 'subject'); }} />
              <button onClick={() => fileInputRef.current?.click()} disabled={uploading}
                style={{ ...styles.docCard, borderStyle: 'dashed', justifyContent: 'center', alignItems: 'center', minHeight: 100, gridColumn: '1 / -1', ...(uploading ? { opacity: 0.6, cursor: 'not-allowed' } : {}) }}>
                {uploading ? <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', color: 'var(--primary)' }} /> : (
                  <><Upload size={20} color="var(--primary)" />
                    <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)' }}>Upload new document</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>PDF, DOCX, DOC, TXT</span></>
                )}
              </button>
            </div>
            {uploadError && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 12 }}><AlertTriangle size={14} /> {uploadError}</div>}
            <div style={styles.navRow}>
              <div />
              <button onClick={handleNext} disabled={!canProceed()} style={styles.nextBtn} id="step1-next">
                Next: Select Standards <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2 ── */}
        {step === 2 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}><ShieldCheck size={20} />Select Standard Documents</h2>
            <p style={styles.stepDesc}>
              Checking: <strong style={{ color: 'var(--primary)' }}>{getSubjectNames()}</strong>
              {recLoading
                ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}> — Analysing document to recommend standards...</span>
                : recommendations.filter(r => r.recommended).length > 0
                  ? <span style={{ color: '#22c55e' }}> — {recommendations.filter(r => r.recommended).length} standards pre-selected based on document analysis.</span>
                  : null
              }
            </p>

            {recLoading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Loader2 size={24} style={{ animation: 'spin 1s linear infinite' }} color="var(--primary)" />
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 10 }}>Analysing document content and matching standards...</div>
              </div>
            ) : (
              <>
                {/* Recommended group */}
                {recDocs.length > 0 && (
                  <div style={{ marginBottom: 20 }}>
                    <div style={styles.groupHeader}>
                      <Star size={14} color="#f0b429" />
                      <span>Recommended for this document ({recDocs.length})</span>
                      <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>Pre-selected based on content analysis</span>
                    </div>
                    <div style={styles.docGrid}>
                      {recDocs.map(renderStandardCard)}
                    </div>
                  </div>
                )}

                {/* Additional group */}
                {addDocs.length > 0 && (
                  <div style={{ marginBottom: 20 }}>
                    <div style={styles.groupHeader}>
                      <ShieldCheck size={14} color="var(--text-muted)" />
                      <span style={{ color: 'var(--text-muted)' }}>Additional Standards ({addDocs.length})</span>
                    </div>
                    <div style={styles.docGrid}>
                      {addDocs.map(renderStandardCard)}
                    </div>
                  </div>
                )}

                {recDocs.length === 0 && addDocs.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                    No standard documents available. Please upload standards first.
                  </div>
                )}

                {/* Select All / None */}
                {(recDocs.length + addDocs.length) > 0 && (
                  <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <button
                      onClick={() => setStandardDocIds([...recDocs, ...addDocs].map(d => d.doc_id))}
                      style={styles.selectAllBtn}
                    >Select All</button>
                    <button onClick={() => setStandardDocIds([])} style={styles.selectAllBtn}>Clear</button>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center' }}>
                      {standardDocIds.length} selected
                    </span>
                  </div>
                )}

                {/* Upload new standard */}
                <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx,.txt" style={{ display: 'none' }}
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleInlineUpload(f, 'standard'); }} />
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading}
                  style={{ ...styles.uploadBtn, ...(uploading ? { opacity: 0.6, cursor: 'not-allowed' } : {}) }}>
                  {uploading ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Upload size={16} />}
                  Upload new standard document
                </button>
              </>
            )}

            {uploadError && <div style={{ color: '#ef4444', fontSize: 12, margin: '8px 0' }}><AlertTriangle size={14} /> {uploadError}</div>}
            <div style={styles.navRow}>
              <button onClick={() => setStep(1)} style={styles.backBtn}>Back</button>
              <button onClick={handleNext} disabled={!canProceed() || recLoading} style={styles.nextBtn} id="step2-next">
                Next: Run Analysis <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3 ── */}
        {step === 3 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}><Search size={20} />Compliance Analysis</h2>
            <p style={styles.stepDesc}>
              Checking <strong style={{ color: 'var(--primary)' }}>{getSubjectNames()}</strong> against {standardDocIds.length} standard{standardDocIds.length !== 1 ? 's' : ''}.
            </p>

            {!running && findings.length === 0 && !error && (
              <div style={{ textAlign: 'center', padding: '32px' }}>
                <button onClick={runCheck} style={styles.runBtn} id="run-compliance-btn">
                  <ShieldCheck size={18} />
                  Run Compliance Check
                </button>
              </div>
            )}

            {/* Loading state with elapsed time */}
            {running && (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: 'var(--primary)' }} />
                <div style={{ fontSize: 15, color: 'var(--text-secondary)', marginTop: 12, fontWeight: 600 }}>
                  Analysing compliance clauses...
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                  <Clock size={12} /> {elapsed}s elapsed — this may take 30–90 seconds
                </div>
              </div>
            )}

            {error && <div style={styles.errorMsg}><AlertTriangle size={14} /> {error}</div>}

            {/* Summary bar */}
            {summary && !running && (
              <div style={styles.summaryBar}>
                {[
                  { label: 'Compliant', val: summary.compliant, color: '#00c853' },
                  { label: 'Non-Compliant', val: summary.non_compliant, color: '#ff4757' },
                  { label: 'Partial', val: summary.partial, color: '#f0b429' },
                  { label: 'Missing', val: summary.missing || 0, color: '#9333ea' },
                  { label: 'Contradiction', val: summary.contradiction || 0, color: '#ef4444' },
                  { label: 'Unverifiable', val: summary.unverifiable, color: '#8899bb' },
                ].map(({ label, val, color }) => (
                  <div key={label} style={styles.summaryItem}>
                    <span style={{ color, fontWeight: 700, fontSize: 20 }}>{val}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Score & Recommendation */}
            {summary && !running && (
              <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                <div style={styles.scoreBadge}>
                  Score: <strong>{summary.score}%</strong>
                </div>
                <div style={{
                  ...styles.recoBadge,
                  background: summary.recommendation === 'APPROVE' ? 'rgba(0,200,83,0.12)' :
                    summary.recommendation === 'REJECT' ? 'rgba(255,71,87,0.12)' : 'rgba(240,180,41,0.12)',
                  color: summary.recommendation === 'APPROVE' ? '#00c853' :
                    summary.recommendation === 'REJECT' ? '#ff4757' : '#f0b429',
                }}>
                  {summary.recommendation}
                </div>
              </div>
            )}

            {/* Findings grouped by topic */}
            {findings.length > 0 && !running && (
              <div style={styles.findingsList}>
                {Object.entries(
                  findings.reduce((acc, f) => {
                    const t = f.topic || 'General Requirements';
                    if (!acc[t]) acc[t] = [];
                    acc[t].push(f);
                    return acc;
                  }, {})
                ).map(([topic, tFindings]) => (
                  <div key={topic} style={{ marginBottom: 24 }}>
                    <h3 style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>
                      {topic}
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                      {tFindings.map((f, i) => {
                        const v = VERDICT_CONFIG[f.verdict] || VERDICT_CONFIG.Unverifiable;
                        const VIcon = v.icon;
                        return (
                          <div key={i} style={{ ...styles.findingCard, borderLeftColor: v.color }}>
                            <div style={styles.findingHeader}>
                              <div style={{ ...styles.verdictBadge, background: v.bg, color: v.color }}>
                                <VIcon size={13} />{v.label}
                              </div>
                              <span style={{ ...styles.findingClause, marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 11 }}>
                                {f.severity !== 'None' && f.severity && (
                                  <span style={{ color: f.severity === 'Critical' ? '#ff4757' : f.severity === 'Major' ? '#f0b429' : 'var(--text-muted)', fontWeight: 700 }}>
                                    {f.severity}
                                  </span>
                                )}
                              </span>
                              <span style={styles.findingClause}>{f.clause_id || f.clause}</span>
                            </div>
                            <div style={styles.findingBody}>
                              {f.requirement && <div style={styles.fieldGroup}><div style={styles.fieldLabel}>Requirement</div><div style={styles.fieldValue}>{f.requirement}</div></div>}
                              {f.finding && <div style={styles.fieldGroup}><div style={styles.fieldLabel}>Finding</div><div style={styles.fieldValue}>{f.finding}</div></div>}
                              {f.recommendation && (
                                <div style={styles.fieldGroup}>
                                  <div style={styles.fieldLabel}>Recommendation</div>
                                  <div style={{ ...styles.fieldValue, color: '#f0b429' }}>{f.recommendation}</div>
                                </div>
                              )}
                              {f.citation && f.citation !== 'N/A' && (
                                <div style={styles.fieldGroup}>
                                  <div style={styles.fieldLabel}>Citation</div>
                                  <div style={{ ...styles.fieldValue, fontStyle: 'italic', background: 'rgba(74,139,255,0.05)', padding: '6px 10px', borderRadius: 6, borderLeft: '2px solid var(--primary)' }}>{f.citation}</div>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Download Report */}
            {downloadUrl && !running && (
              <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <a href={getApiUrl(downloadUrl)} style={styles.downloadReportBtn} target="_blank" rel="noopener noreferrer">
                  <Download size={18} />Download Compliance Report (.docx)
                </a>
              </div>
            )}

            <div style={styles.navRow}>
              <button onClick={() => setStep(2)} style={styles.backBtn} disabled={running}>Back</button>
              {findings.length > 0 && !running && (
                <button
                  onClick={() => { setFindings([]); setSummary(null); setDownloadUrl(null); setError(''); runCheck(); }}
                  style={styles.rerunBtn}
                >Re-run Analysis</button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  page: { padding: '28px 32px', maxWidth: '960px', margin: '0 auto', minHeight: '100vh' },
  header: { display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '24px' },
  backLink: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 38, height: 38, borderRadius: 'var(--radius-md)',
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    color: 'var(--text-secondary)', textDecoration: 'none', flexShrink: 0,
  },
  title: { fontSize: '22px', fontWeight: 700, color: 'var(--text-heading)', margin: 0 },
  subtitle: { fontSize: '13px', color: 'var(--text-muted)', margin: 0 },
  steps: {
    display: 'flex', gap: '4px', marginBottom: '24px',
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)', padding: '12px 16px',
  },
  stepItem: { display: 'flex', alignItems: 'center', gap: '8px', flex: 1, color: 'var(--text-muted)', padding: '6px 0' },
  stepActive: { color: 'var(--text-primary)' },
  stepCurrent: { color: 'var(--primary)' },
  stepCircle: { width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', fontSize: '12px', fontWeight: 700, flexShrink: 0 },
  card: { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '24px', boxShadow: 'var(--shadow-md)' },
  stepTitle: { display: 'flex', alignItems: 'center', gap: '10px', fontSize: '18px', fontWeight: 700, color: 'var(--text-heading)', marginBottom: '8px' },
  stepDesc: { fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: '1.6' },
  docGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '10px', marginBottom: '12px' },
  docCard: {
    display: 'flex', flexDirection: 'column', gap: '4px', padding: '14px',
    border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
    cursor: 'pointer', transition: 'border-color 0.15s, background 0.15s',
  },
  docCardName: { fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  docCardMeta: { fontSize: '11px', color: 'var(--text-muted)' },
  groupHeader: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
    marginBottom: 8, paddingBottom: 6, borderBottom: '1px solid var(--border)',
  },
  recBadge: {
    display: 'inline-flex', alignItems: 'center', gap: 3,
    fontSize: 10, fontWeight: 700, color: '#f0b429',
    background: 'rgba(240,180,41,0.12)', padding: '2px 6px',
    borderRadius: 8,
  },
  selectAllBtn: {
    padding: '5px 12px', fontSize: 12, fontWeight: 500,
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)', color: 'var(--text-secondary)', cursor: 'pointer',
  },
  uploadBtn: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
    fontSize: 13, fontWeight: 500, background: 'transparent',
    border: '1px dashed var(--border)', borderRadius: 'var(--radius-md)',
    color: 'var(--text-muted)', cursor: 'pointer', width: '100%', justifyContent: 'center',
    marginBottom: 12,
  },
  navRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '16px', borderTop: '1px solid var(--border)', marginTop: '8px' },
  nextBtn: { display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 20px', background: 'var(--primary)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer' },
  backBtn: { padding: '10px 20px', background: 'transparent', color: 'var(--text-secondary)', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 500, border: '1px solid var(--border)', cursor: 'pointer' },
  runBtn: { display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '14px 32px', background: 'linear-gradient(135deg, #4a8bff, #3a6fd8)', color: '#fff', borderRadius: 'var(--radius-lg)', fontSize: '15px', fontWeight: 700, border: 'none', boxShadow: '0 4px 20px rgba(74,139,255,0.3)', cursor: 'pointer' },
  rerunBtn: { padding: '10px 20px', background: 'rgba(74,139,255,0.1)', color: 'var(--primary)', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, border: '1px solid rgba(74,139,255,0.25)', cursor: 'pointer' },
  findingsList: { display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' },
  findingCard: { background: 'var(--bg-input)', border: '1px solid var(--border)', borderLeft: '4px solid', borderRadius: 'var(--radius-md)', overflow: 'hidden' },
  findingHeader: { display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' },
  verdictBadge: { display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 10px', borderRadius: '10px', fontSize: '11px', fontWeight: 700 },
  findingClause: { fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' },
  findingBody: { padding: '12px 14px' },
  fieldGroup: { marginBottom: '8px' },
  fieldLabel: { fontSize: '10px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.3px', marginBottom: '2px' },
  fieldValue: { fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.6' },
  summaryBar: { display: 'flex', gap: '12px', padding: '14px', background: 'var(--bg-surface)', borderRadius: 'var(--radius-md)', marginBottom: '12px', justifyContent: 'center', flexWrap: 'wrap' },
  summaryItem: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px', minWidth: '72px' },
  scoreBadge: { padding: '6px 14px', background: 'rgba(74,139,255,0.1)', border: '1px solid rgba(74,139,255,0.2)', borderRadius: 8, fontSize: 13, color: 'var(--primary)' },
  recoBadge: { padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 700, border: '1px solid transparent' },
  downloadReportBtn: { display: 'inline-flex', alignItems: 'center', gap: '10px', padding: '12px 28px', background: 'linear-gradient(135deg, #00c853, #00a843)', color: '#fff', borderRadius: 'var(--radius-lg)', fontSize: '14px', fontWeight: 700, textDecoration: 'none', boxShadow: '0 4px 20px rgba(0,200,83,0.25)' },
  errorMsg: { display: 'flex', alignItems: 'center', gap: 6, padding: '10px 14px', background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.25)', borderRadius: 'var(--radius-md)', color: '#ff4757', fontSize: '13px', marginBottom: '16px' },
};
