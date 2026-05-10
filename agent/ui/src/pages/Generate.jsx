/**
 * AGRA Agent — Generate Page
 * Content generation: PPT, Summary, Quiz with tabbed interface.
 */

import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, Presentation, FileText, HelpCircle, Download,
  Loader2, CheckCircle2, Sliders, BookOpen,
} from 'lucide-react';
import api, { getApiUrl } from '../utils/api';
import { connectStream } from '../utils/stream';
import { renderMarkdown } from '../utils/markdown';

const TABS = [
  { id: 'ppt', label: 'PPT', icon: Presentation },
  { id: 'summary', label: 'Summary', icon: FileText },
  { id: 'quiz', label: 'Quiz', icon: HelpCircle },
];

export default function GeneratePage() {
  const [activeTab, setActiveTab] = useState('ppt');
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/documents')
      .then(({ data }) => setDocuments(data.documents || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <Link to="/" style={styles.backLink}><ArrowLeft size={18} /></Link>
        <div>
          <h1 style={styles.title}>Content Generator</h1>
          <p style={styles.subtitle}>Create presentations, summaries, and quizzes from your documents</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        {TABS.map(tab => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                ...styles.tab,
                ...(activeTab === tab.id ? styles.tabActive : {}),
              }}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div style={styles.content}>
        {activeTab === 'ppt' && <PPTGenerator documents={documents} />}
        {activeTab === 'summary' && <SummaryGenerator documents={documents} />}
        {activeTab === 'quiz' && <QuizGenerator documents={documents} />}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   PPT GENERATOR
   ═══════════════════════════════════════════════════════════════ */
function PPTGenerator({ documents }) {
  const [topic, setTopic] = useState('');
  const [numSlides, setNumSlides] = useState(10);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [styleNotes, setStyleNotes] = useState('');
  const [generating, setGenerating] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [error, setError] = useState('');

  const toggleDoc = (docId) => {
    setSelectedDocs(prev =>
      prev.includes(docId) ? prev.filter(d => d !== docId) : [...prev, docId]
    );
  };

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setGenerating(true);
    setDownloadUrl(null);
    setError('');
    try {
      const { data } = await api.post('/generate/ppt', {
        topic: topic.trim(),
        num_slides: numSlides,
        doc_ids: selectedDocs,
        style_notes: styleNotes || null,
      }, { responseType: 'blob' });

      const url = window.URL.createObjectURL(data);
      setDownloadUrl(url);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={styles.generatorCard}>
      <div style={styles.formGroup}>
        <label style={styles.label}>Topic / Title</label>
        <input
          value={topic}
          onChange={e => setTopic(e.target.value)}
          placeholder="e.g. Maritime Safety Protocols 2024"
          style={styles.input}
          id="ppt-topic"
        />
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Number of Slides: <strong style={{ color: 'var(--primary)' }}>{numSlides}</strong></label>
        <div style={styles.sliderRow}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>5</span>
          <input
            type="range"
            min={5}
            max={20}
            value={numSlides}
            onChange={e => setNumSlides(Number(e.target.value))}
            style={styles.slider}
          />
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>20</span>
        </div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Reference Documents (optional)</label>
        <div style={styles.docCheckboxes}>
          {documents.map(doc => (
            <label key={doc.doc_id} style={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={selectedDocs.includes(doc.doc_id)}
                onChange={() => toggleDoc(doc.doc_id)}
                style={styles.checkbox}
              />
              <span>{doc.filename}</span>
            </label>
          ))}
          {documents.length === 0 && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No documents indexed</span>
          )}
        </div>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Style Notes (optional)</label>
        <textarea
          value={styleNotes}
          onChange={e => setStyleNotes(e.target.value)}
          placeholder="e.g. Professional, include statistics, focus on safety compliance..."
          rows={3}
          style={styles.textarea}
        />
      </div>

      {error && <div style={styles.errorMsg}>{error}</div>}

      <div style={styles.actionRow}>
        <button
          onClick={handleGenerate}
          disabled={!topic.trim() || generating}
          style={styles.generateBtn}
          id="generate-ppt-btn"
        >
          {generating ? (
            <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
          ) : (
            <><Presentation size={16} /> Generate PPT</>
          )}
        </button>

        {downloadUrl && (
          <a
            href={downloadUrl}
            download={`AGRA_${topic.slice(0, 30).replace(/ /g, '_')}.pptx`}
            style={styles.downloadBtn}
          >
            <Download size={16} /> Download .pptx
          </a>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   SUMMARY GENERATOR
   ═══════════════════════════════════════════════════════════════ */
function SummaryGenerator({ documents }) {
  const [selectedDoc, setSelectedDoc] = useState('');
  const [summaryType, setSummaryType] = useState('executive');
  const [generating, setGenerating] = useState(false);
  const [summaryText, setSummaryText] = useState('');
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [error, setError] = useState('');

  const handleGenerate = () => {
    if (!selectedDoc) return;
    setGenerating(true);
    setSummaryText('');
    setDownloadUrl(null);
    setError('');

    let accumulated = '';

    connectStream(
      getApiUrl('/api/agent/generate/summary'),
      { doc_id: selectedDoc, summary_type: summaryType },
      (data) => {
        if (data.token) {
          accumulated += data.token;
          setSummaryText(accumulated);
        }
      },
      (data) => {
        setGenerating(false);
        if (data.download_url) {
          setDownloadUrl(getApiUrl(data.download_url));
        }
      },
      (err) => {
        setGenerating(false);
        setError(err.message);
      }
    );
  };

  return (
    <div style={styles.generatorCard}>
      <div style={styles.formGroup}>
        <label style={styles.label}>Select Document</label>
        <select
          value={selectedDoc}
          onChange={e => setSelectedDoc(e.target.value)}
          style={styles.select}
          id="summary-doc-select"
        >
          <option value="">— Choose a document —</option>
          {documents.map(doc => (
            <option key={doc.doc_id} value={doc.doc_id}>{doc.filename}</option>
          ))}
        </select>
      </div>

      <div style={styles.formGroup}>
        <label style={styles.label}>Summary Type</label>
        <div style={styles.radioGroup}>
          {[
            { value: 'executive', label: 'Executive Summary', desc: 'High-level overview for leadership' },
            { value: 'technical', label: 'Technical Summary', desc: 'Detailed technical analysis' },
          ].map(opt => (
            <label
              key={opt.value}
              style={{
                ...styles.radioCard,
                borderColor: summaryType === opt.value ? 'var(--primary)' : 'var(--border)',
                background: summaryType === opt.value ? 'var(--primary-dim)' : 'transparent',
              }}
            >
              <input
                type="radio"
                name="summaryType"
                value={opt.value}
                checked={summaryType === opt.value}
                onChange={e => setSummaryType(e.target.value)}
                style={{ display: 'none' }}
              />
              <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>{opt.label}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{opt.desc}</div>
            </label>
          ))}
        </div>
      </div>

      {error && <div style={styles.errorMsg}>{error}</div>}

      <div style={styles.actionRow}>
        <button
          onClick={handleGenerate}
          disabled={!selectedDoc || generating}
          style={styles.generateBtn}
          id="generate-summary-btn"
        >
          {generating ? (
            <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
          ) : (
            <><FileText size={16} /> Generate Summary</>
          )}
        </button>
        {downloadUrl && (
          <a href={downloadUrl} style={styles.downloadBtn} target="_blank" rel="noopener">
            <Download size={16} /> Download .docx
          </a>
        )}
      </div>

      {/* Preview Panel */}
      {summaryText && (
        <div style={styles.previewPanel}>
          <div style={styles.previewHeader}>
            <BookOpen size={14} />
            <span>Summary Preview</span>
            {generating && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite', marginLeft: 'auto' }} />}
          </div>
          <div
            className="md-content"
            style={styles.previewContent}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(summaryText) }}
          />
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   QUIZ GENERATOR
   ═══════════════════════════════════════════════════════════════ */
function QuizGenerator({ documents }) {
  const [selectedDoc, setSelectedDoc] = useState('');
  const [numMcq, setNumMcq] = useState(5);
  const [numShort, setNumShort] = useState(3);
  const [generating, setGenerating] = useState(false);
  const [quizData, setQuizData] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [error, setError] = useState('');

  const handleGenerate = async () => {
    if (!selectedDoc) return;
    setGenerating(true);
    setQuizData(null);
    setDownloadUrl(null);
    setError('');
    try {
      const { data } = await api.post('/generate/quiz', {
        doc_id: selectedDoc,
        num_mcq: numMcq,
        num_short_answer: numShort,
      });
      setQuizData(data.quiz);
      setDownloadUrl(data.download_url ? getApiUrl(data.download_url) : null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={styles.generatorCard}>
      <div style={styles.formGroup}>
        <label style={styles.label}>Select Document</label>
        <select
          value={selectedDoc}
          onChange={e => setSelectedDoc(e.target.value)}
          style={styles.select}
          id="quiz-doc-select"
        >
          <option value="">— Choose a document —</option>
          {documents.map(doc => (
            <option key={doc.doc_id} value={doc.doc_id}>{doc.filename}</option>
          ))}
        </select>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div style={styles.formGroup}>
          <label style={styles.label}>Multiple Choice Questions</label>
          <div style={styles.numberInputRow}>
            <button onClick={() => setNumMcq(Math.max(1, numMcq - 1))} style={styles.numBtn}>−</button>
            <span style={styles.numValue}>{numMcq}</span>
            <button onClick={() => setNumMcq(Math.min(20, numMcq + 1))} style={styles.numBtn}>+</button>
          </div>
        </div>
        <div style={styles.formGroup}>
          <label style={styles.label}>Short Answer Questions</label>
          <div style={styles.numberInputRow}>
            <button onClick={() => setNumShort(Math.max(0, numShort - 1))} style={styles.numBtn}>−</button>
            <span style={styles.numValue}>{numShort}</span>
            <button onClick={() => setNumShort(Math.min(10, numShort + 1))} style={styles.numBtn}>+</button>
          </div>
        </div>
      </div>

      {error && <div style={styles.errorMsg}>{error}</div>}

      <div style={styles.actionRow}>
        <button
          onClick={handleGenerate}
          disabled={!selectedDoc || generating}
          style={styles.generateBtn}
          id="generate-quiz-btn"
        >
          {generating ? (
            <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Generating...</>
          ) : (
            <><HelpCircle size={16} /> Generate Quiz</>
          )}
        </button>
        {downloadUrl && (
          <a href={downloadUrl} style={styles.downloadBtn} target="_blank" rel="noopener">
            <Download size={16} /> Download .docx
          </a>
        )}
      </div>

      {/* Quiz Preview */}
      {quizData && (
        <div style={styles.previewPanel}>
          <div style={styles.previewHeader}>
            <HelpCircle size={14} />
            <span>{quizData.title || 'Quiz Preview'}</span>
          </div>
          <div style={styles.previewContent}>
            {quizData.mcq?.length > 0 && (
              <>
                <h3 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--primary)', margin: '0 0 12px' }}>
                  Multiple Choice Questions
                </h3>
                {quizData.mcq.map((q, i) => (
                  <div key={i} style={styles.quizQuestion}>
                    <div style={styles.qNum}>Q{i + 1}.</div>
                    <div>
                      <div style={{ fontWeight: 500, marginBottom: '6px', color: 'var(--text-primary)' }}>{q.question}</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px' }}>
                        {Object.entries(q.options || {}).map(([key, val]) => (
                          <div
                            key={key}
                            style={{
                              fontSize: '12px',
                              padding: '4px 8px',
                              borderRadius: '4px',
                              color: key === q.correct ? '#00c853' : 'var(--text-secondary)',
                              background: key === q.correct ? 'rgba(0,200,83,0.1)' : 'transparent',
                              fontWeight: key === q.correct ? 600 : 400,
                            }}
                          >
                            {key}) {val}
                          </div>
                        ))}
                      </div>
                      {q.explanation && (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '6px', fontStyle: 'italic' }}>
                          💡 {q.explanation}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </>
            )}

            {quizData.short_answer?.length > 0 && (
              <>
                <h3 style={{ fontSize: '14px', fontWeight: 700, color: 'var(--primary)', margin: '20px 0 12px' }}>
                  Short Answer Questions
                </h3>
                {quizData.short_answer.map((q, i) => (
                  <div key={i} style={styles.quizQuestion}>
                    <div style={styles.qNum}>Q{i + 1}.</div>
                    <div>
                      <div style={{ fontWeight: 500, marginBottom: '4px', color: 'var(--text-primary)' }}>{q.question}</div>
                      <div style={{ fontSize: '12px', color: 'var(--accent-green)', background: 'rgba(0,200,83,0.06)', padding: '8px', borderRadius: '6px' }}>
                        <strong>Model Answer:</strong> {q.model_answer}
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   STYLES
   ═══════════════════════════════════════════════════════════════ */
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

  /* Tabs */
  tabs: {
    display: 'flex',
    gap: '4px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '4px',
    marginBottom: '24px',
  },
  tab: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flex: 1,
    justifyContent: 'center',
    padding: '10px 16px',
    borderRadius: 'var(--radius-md)',
    background: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: '13px',
    fontWeight: 600,
    border: 'none',
  },
  tabActive: {
    background: 'var(--primary)',
    color: '#fff',
  },

  content: {},

  /* Generator Card */
  generatorCard: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '24px',
    boxShadow: 'var(--shadow-md)',
  },

  /* Form */
  formGroup: {
    marginBottom: '20px',
  },
  label: {
    display: 'block',
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    marginBottom: '8px',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-primary)',
    fontSize: '14px',
  },
  textarea: {
    width: '100%',
    padding: '10px 14px',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    resize: 'vertical',
    fontFamily: 'var(--font-sans)',
    minHeight: '60px',
  },
  select: {
    width: '100%',
    padding: '10px 14px',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-primary)',
    fontSize: '14px',
    appearance: 'none',
  },
  sliderRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  slider: {
    flex: 1,
    accentColor: 'var(--primary)',
    height: '4px',
  },
  docCheckboxes: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    maxHeight: '180px',
    overflowY: 'auto',
    padding: '8px',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '13px',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    padding: '4px 0',
  },
  checkbox: {
    accentColor: 'var(--primary)',
  },
  radioGroup: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '10px',
  },
  radioCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    padding: '12px 14px',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    transition: 'border-color 0.15s, background 0.15s',
  },
  numberInputRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  numBtn: {
    width: 34,
    height: 34,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-input)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: '16px',
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  numValue: {
    fontSize: '18px',
    fontWeight: 700,
    color: 'var(--primary)',
    minWidth: '32px',
    textAlign: 'center',
  },

  /* Actions */
  actionRow: {
    display: 'flex',
    gap: '12px',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  generateBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '11px 22px',
    background: 'var(--primary)',
    color: '#fff',
    borderRadius: 'var(--radius-md)',
    fontSize: '13px',
    fontWeight: 600,
    border: 'none',
  },
  downloadBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '11px 22px',
    background: 'rgba(0, 200, 83, 0.12)',
    color: '#00c853',
    borderRadius: 'var(--radius-md)',
    fontSize: '13px',
    fontWeight: 600,
    textDecoration: 'none',
    border: '1px solid rgba(0, 200, 83, 0.25)',
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

  /* Preview */
  previewPanel: {
    marginTop: '24px',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    overflow: 'hidden',
  },
  previewHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 16px',
    background: 'var(--bg-surface)',
    borderBottom: '1px solid var(--border)',
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  previewContent: {
    padding: '16px',
    fontSize: '13px',
    lineHeight: '1.7',
    maxHeight: '500px',
    overflowY: 'auto',
  },
  quizQuestion: {
    display: 'flex',
    gap: '10px',
    padding: '12px 0',
    borderBottom: '1px solid var(--border)',
    fontSize: '13px',
  },
  qNum: {
    fontWeight: 700,
    color: 'var(--primary)',
    fontSize: '13px',
    minWidth: '28px',
  },
};
