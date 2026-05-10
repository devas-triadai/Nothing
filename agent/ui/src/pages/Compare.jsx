import { useState, useEffect, useRef } from 'react';
import { useLocation, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, GitCompare, FileText, CheckCircle2, ChevronRight, Search, Loader2, Download, AlertTriangle } from 'lucide-react';
import api, { getApiUrl } from '../utils/api';
import { connectStream } from '../utils/stream';

export default function ComparePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const preSelectedDocs = location.state?.selectedDocIds || [];

  const [step, setStep] = useState(preSelectedDocs.length >= 2 ? 2 : 1);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  // Step 1: Bids
  const [bidDocIds, setBidDocIds] = useState(preSelectedDocs);
  // Step 2: Standard (Optional)
  const [standardDocId, setStandardDocId] = useState(null);
  
  // State for streaming analysis
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [comparisonText, setComparisonText] = useState('');
  const [downloadUrl, setDownloadUrl] = useState(null);

  useEffect(() => {
    api.get('/documents')
      .then(({ data }) => setDocuments(data.documents || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const toggleBid = (docId) => {
    setBidDocIds(prev => prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]);
  };

  const handleNext = () => {
    if (step === 1 && bidDocIds.length >= 2) setStep(2);
    else if (step === 2) setStep(3);
  };

  const runComparison = () => {
    setRunning(true);
    setComparisonText('');
    setError('');
    setDownloadUrl(null);
    setStep(3);

    const payload = {
      bid_doc_ids: bidDocIds,
      standard_doc_id: standardDocId || null
    };

    connectStream(
      getApiUrl('/api/agent/compare/bids'),
      payload,
      (data) => {
        if (data.token) {
          setComparisonText(prev => prev + data.token);
        }
      },
      (data) => {
        setRunning(false);
        if (data.download_url) setDownloadUrl(data.download_url);
      },
      (err) => {
        setRunning(false);
        setError(err.message);
      }
    );
  };

  const getDocName = (id) => documents.find(d => d.doc_id === id)?.filename || id;

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <button onClick={() => navigate(-1)} style={styles.backLink}><ArrowLeft size={18} /></button>
        <div>
          <h1 style={styles.title}>Comparative Analysis</h1>
          <p style={styles.subtitle}>Cross-document reasoning and bid vs standard evaluation</p>
        </div>
      </div>

      <div style={styles.steps}>
        {[
          { n: 1, label: 'Select Bids/Proposals' },
          { n: 2, label: 'Select Standard (Optional)' },
          { n: 3, label: 'Comparison Matrix' },
        ].map(({ n, label }) => (
          <div key={n} style={{...styles.stepItem, ...(step >= n ? styles.stepActive : {}), ...(step === n ? styles.stepCurrent : {})}}>
            <div style={{...styles.stepCircle, background: step >= n ? 'var(--primary)' : 'var(--border)', color: step >= n ? '#fff' : 'var(--text-muted)'}}>
              {n}
            </div>
            <span style={{ fontSize: '12px', fontWeight: step === n ? 600 : 400 }}>{label}</span>
          </div>
        ))}
      </div>

      <div style={styles.card}>
        {step === 1 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}><GitCompare size={20} /> Select Documents to Compare</h2>
            <p style={styles.stepDesc}>Choose at least 2 bid documents, technical proposals, or drawings to compare against each other.</p>
            
            <div style={styles.docGrid}>
              {loading ? (
                <div style={{ textAlign: 'center', padding: '40px', width: '100%' }}>
                  <Loader2 size={24} style={{ animation: 'spin 1s linear infinite' }} color="var(--primary)" />
                </div>
              ) : documents.map(doc => (
                <div
                  key={doc.doc_id}
                  style={{
                    ...styles.docCard,
                    borderColor: bidDocIds.includes(doc.doc_id) ? 'var(--primary)' : 'var(--border)',
                    background: bidDocIds.includes(doc.doc_id) ? 'rgba(74,139,255,0.05)' : 'var(--bg-card)',
                  }}
                  onClick={() => toggleBid(doc.doc_id)}
                >
                  <input type="checkbox" checked={bidDocIds.includes(doc.doc_id)} readOnly style={{ accentColor: 'var(--primary)', width: 16, height: 16 }} />
                  <div style={styles.docCardName}>{doc.filename}</div>
                  <div style={{ fontSize: '11px', color: 'var(--accent-blue-light)', fontWeight: 600 }}>{doc.category || 'Uncategorised'}</div>
                </div>
              ))}
            </div>
            <div style={styles.navRow}>
              <div />
              <button onClick={handleNext} disabled={bidDocIds.length < 2} style={styles.nextBtn}>
                Next Step <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}><CheckCircle2 size={20} /> Select Baseline Standard (Optional)</h2>
            <p style={styles.stepDesc}>Choose an SOTR, IMO Standard, or specific requirement document to evaluate the selected bids against. Skip if you only want to compare the bids to each other.</p>
            
            <div style={{ marginBottom: 16, padding: 12, background: 'rgba(74,139,255,0.05)', borderRadius: 8, border: '1px solid rgba(74,139,255,0.2)' }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>Selected Bids:</span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                {bidDocIds.map(id => (
                  <span key={id} style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 4, padding: '2px 8px', fontSize: 11, color: 'var(--text-primary)' }}>
                    {getDocName(id)}
                  </span>
                ))}
              </div>
            </div>

            <div style={styles.docGrid}>
              <div
                style={{ ...styles.docCard, borderColor: !standardDocId ? 'var(--primary)' : 'var(--border)', background: !standardDocId ? 'rgba(74,139,255,0.05)' : 'var(--bg-card)' }}
                onClick={() => setStandardDocId(null)}
              >
                <div style={styles.radioCircle}>{!standardDocId && <div style={styles.radioInner} />}</div>
                <div style={{...styles.docCardName, fontWeight: 600}}>None (Bid vs Bid only)</div>
              </div>

              {documents.filter(d => !bidDocIds.includes(d.doc_id)).map(doc => (
                <div
                  key={doc.doc_id}
                  style={{ ...styles.docCard, borderColor: standardDocId === doc.doc_id ? 'var(--primary)' : 'var(--border)', background: standardDocId === doc.doc_id ? 'rgba(74,139,255,0.05)' : 'var(--bg-card)' }}
                  onClick={() => setStandardDocId(doc.doc_id)}
                >
                  <div style={styles.radioCircle}>{standardDocId === doc.doc_id && <div style={styles.radioInner} />}</div>
                  <div style={styles.docCardName}>{doc.filename}</div>
                  <div style={{ fontSize: '11px', color: doc.category?.includes('Standard') || doc.category === 'SOTR' ? '#22c55e' : 'var(--accent-blue-light)', fontWeight: 600 }}>{doc.category || 'Uncategorised'}</div>
                </div>
              ))}
            </div>

            <div style={styles.navRow}>
              <button onClick={() => setStep(1)} style={styles.backBtn}>Back</button>
              <button onClick={runComparison} style={styles.runBtn}>
                <Search size={16} /> Run Comparison
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="animate-fade-in">
            <h2 style={styles.stepTitle}><Search size={20} /> Analysis Results</h2>
            <p style={styles.stepDesc}>Comparing {bidDocIds.length} bids{standardDocId ? ' against the selected baseline standard' : ''}.</p>

            {error && <div style={styles.errorMsg}><AlertTriangle size={16}/> {error}</div>}

            <div style={{ 
              background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', 
              padding: '24px', minHeight: '300px', whiteSpace: 'pre-wrap', fontFamily: 'var(--font-sans)',
              fontSize: '14px', lineHeight: '1.6', color: 'var(--text-primary)', overflowX: 'auto'
            }}>
              {comparisonText ? (
                // Super basic markdown parsing for the streamed matrix
                <div dangerouslySetInnerHTML={{ __html: comparisonText
                  .replace(/^### (.*$)/gim, '<h3>$1</h3>')
                  .replace(/^## (.*$)/gim, '<h2>$1</h2>')
                  .replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>')
                  .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                  .replace(/\*(.*?)\*/g, '<em>$1</em>')
                  .replace(/\|(.+)\|/g, (match) => {
                     // Table formatting
                     if(match.includes('---')) return '';
                     return `<div style="display:flex;border-bottom:1px solid var(--border);padding:8px 0">${match.split('|').filter(s=>s.trim()).map(cell => `<div style="flex:1;padding:0 8px">${cell.trim()}</div>`).join('')}</div>`;
                  })
                }} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', paddingTop: 60 }}>
                  <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', marginBottom: 16 }} color="var(--primary)" />
                  Generating comparative analysis matrix...
                </div>
              )}
            </div>

            <div style={{...styles.navRow, marginTop: 24}}>
              <button onClick={() => { setStep(2); setComparisonText(''); }} style={styles.backBtn}>Modify Selection</button>
              {downloadUrl && !running && (
                <a href={getApiUrl(downloadUrl)} style={styles.downloadBtn} target="_blank" rel="noopener noreferrer">
                  <Download size={16} /> Download Matrix (.csv)
                </a>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  page: { padding: '28px 32px', maxWidth: '1000px', margin: '0 auto', minHeight: '100vh' },
  header: { display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '24px' },
  backLink: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 38, height: 38, borderRadius: 'var(--radius-md)', background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-secondary)', cursor: 'pointer' },
  title: { fontSize: '22px', fontWeight: 700, color: 'var(--text-heading)', margin: 0 },
  subtitle: { fontSize: '13px', color: 'var(--text-muted)', margin: 0 },
  steps: { display: 'flex', gap: '4px', marginBottom: '24px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '12px 16px' },
  stepItem: { display: 'flex', alignItems: 'center', gap: '8px', flex: 1, color: 'var(--text-muted)', padding: '6px 0' },
  stepActive: { color: 'var(--text-primary)' },
  stepCurrent: { color: 'var(--primary)' },
  stepCircle: { width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', fontSize: '12px', fontWeight: 700, flexShrink: 0 },
  card: { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '24px', boxShadow: 'var(--shadow-md)' },
  stepTitle: { display: 'flex', alignItems: 'center', gap: '10px', fontSize: '18px', fontWeight: 700, color: 'var(--text-heading)', marginBottom: '8px' },
  stepDesc: { fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: '1.6' },
  docGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '10px', marginBottom: '20px' },
  docCard: { display: 'flex', flexDirection: 'column', gap: '4px', padding: '14px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', cursor: 'pointer', transition: 'all 0.15s' },
  docCardName: { fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  radioCircle: { width: 16, height: 16, borderRadius: '50%', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  radioInner: { width: 8, height: 8, borderRadius: '50%', background: 'var(--primary)' },
  navRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '16px', borderTop: '1px solid var(--border)', marginTop: '8px' },
  nextBtn: { display: 'flex', alignItems: 'center', gap: '6px', padding: '10px 20px', background: 'var(--primary)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer' },
  backBtn: { padding: '10px 20px', background: 'transparent', color: 'var(--text-secondary)', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 500, border: '1px solid var(--border)', cursor: 'pointer' },
  runBtn: { display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', background: 'linear-gradient(135deg, #4a8bff, #3a6fd8)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, border: 'none', cursor: 'pointer' },
  downloadBtn: { display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', background: 'var(--accent-green)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, textDecoration: 'none' },
  errorMsg: { padding: '12px', background: 'rgba(239,68,68,0.1)', color: '#ef4444', borderRadius: '8px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }
};
