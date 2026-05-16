/**
 * AGRA Agent — Chat Page
 * Unified chat UI: Q&A, PPT generation, quiz, summary — all from the prompt.
 * Perplexity-style numbered citations with clickable source pills.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  MessageSquare, Plus, Send, Paperclip, ChevronDown, ChevronRight,
  FileText, ShieldCheck, LogOut, User, Loader2, X, Bot, Sparkles,
  Presentation, ClipboardList, BookOpen, Download, CheckCircle, XCircle,
  ExternalLink, ChevronLeft, Sun, Moon, LayoutDashboard, AlertTriangle, Edit2,
  Upload, FolderOpen,
} from 'lucide-react';
import { getToken, getUser, decodeToken, logout, getDashboardUrl } from '../utils/auth';
import api, { getApiUrl } from '../utils/api';
import { connectStream } from '../utils/stream';
import { renderMarkdown } from '../utils/markdown';
import { useTheme } from '../utils/ThemeContext';
import ComparisonCard from '../components/ComparisonCard';
import ComplianceCard from '../components/ComplianceCard'; // Workstream E

// ── Timestamp formatter ──
function formatTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' +
    d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const SESSIONS_KEY = 'agra_chat_sessions';
const ACTIVE_KEY = 'agra_active_session';

function loadSessions() {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) || '[]'); }
  catch { return []; }
}
function saveSessions(sessions) {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
}
function newSessionId() {
  return 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
}

// ── Citation chip renderer ──
// Replaces [1], [2] in text with styled superscript chips linked to sources
function renderWithCitations(html, sources, onCiteClick) {
  if (!sources || sources.length === 0) return html;
  return html.replace(/\[(\d+)\]/g, (match, num) => {
    const idx = parseInt(num) - 1;
    if (idx >= 0 && idx < sources.length) {
      return `<sup class="cite-chip" data-cite="${idx}" title="${sources[idx]?.document || ''} · p.${sources[idx]?.page || '?'}">[${num}]</sup>`;
    }
    return match;
  });
}

// ── Inline Quiz Component ──
function InlineQuiz({ quiz }) {
  const [answers, setAnswers] = useState({});
  const [revealed, setRevealed] = useState({});

  const select = (qi, opt) => setAnswers(p => ({ ...p, [qi]: opt }));
  const reveal = (qi) => setRevealed(p => ({ ...p, [qi]: true }));

  if (!quiz?.mcq) return null;

  return (
    <div style={quizStyles.container}>
      <div style={quizStyles.header}>
        <ClipboardList size={16} color="#7c6ef7" />
        <span style={quizStyles.headerText}>{quiz.title || 'Knowledge Quiz'}</span>
        <span style={quizStyles.badge}>{quiz.mcq.length} MCQ{quiz.short_answer?.length ? ` · ${quiz.short_answer.length} Short Answer` : ''}</span>
      </div>

      {quiz.mcq.map((q, qi) => {
        const chosen = answers[qi];
        const isRevealed = revealed[qi];
        const isCorrect = chosen === q.correct;
        return (
          <div key={qi} style={quizStyles.question}>
            <p style={quizStyles.questionText}><strong>Q{qi + 1}.</strong> {q.question}</p>
            <div style={quizStyles.options}>
              {Object.entries(q.options || {}).map(([key, val]) => {
                let bg = 'var(--bg-card)';
                let border = 'var(--border)';
                let color = 'var(--text-secondary)';
                if (chosen === key) {
                  if (isRevealed) {
                    bg = isCorrect ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)';
                    border = isCorrect ? '#22c55e' : '#ef4444';
                    color = isCorrect ? '#22c55e' : '#ef4444';
                  } else {
                    bg = 'rgba(124, 110, 247, 0.1)';
                    border = '#7c6ef7';
                    color = '#7c6ef7';
                  }
                } else if (isRevealed && key === q.correct) {
                  bg = 'rgba(34, 197, 94, 0.08)';
                  border = '#22c55e';
                  color = '#22c55e';
                }
                return (
                  <button
                    key={key}
                    onClick={() => !isRevealed && select(qi, key)}
                    style={{ ...quizStyles.option, background: bg, borderColor: border, color }}
                  >
                    <span style={quizStyles.optKey}>{key}</span>
                    {val}
                  </button>
                );
              })}
            </div>
            {isRevealed && (
              <div style={quizStyles.explanation}>
                {isCorrect ? <CheckCircle size={13} color="#22c55e" /> : <XCircle size={13} color="#ef4444" />}
                <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {isCorrect ? 'Correct! ' : `Incorrect. Correct: ${q.correct}. `}
                  {q.explanation}
                </span>
              </div>
            )}
            {chosen && !isRevealed && (
              <button onClick={() => reveal(qi)} style={quizStyles.revealBtn}>
                Reveal Answer
              </button>
            )}
          </div>
        );
      })}

      {quiz.short_answer?.map((q, qi) => (
        <div key={`sa-${qi}`} style={quizStyles.question}>
          <p style={quizStyles.questionText}><strong>SA{qi + 1}.</strong> {q.question}</p>
          <details style={quizStyles.details}>
            <summary style={quizStyles.summary}>Show model answer</summary>
            <p style={quizStyles.modelAnswer}>{q.model_answer}</p>
          </details>
        </div>
      ))}
    </div>
  );
}

// ── PPT Card Component ──
function PPTCard({ filename, slides, downloadUrl, topic, version, onRefine }) {
  return (
    <div style={pptStyles.card}>
      <div style={pptStyles.icon}><Presentation size={28} color="var(--primary)" /></div>
      <div style={pptStyles.info}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={pptStyles.title}>{topic || filename}</span>
          {version && version > 1 && (
            <span style={{
              fontSize: '10px', fontWeight: 700, color: '#fff',
              background: 'var(--primary)', borderRadius: '4px',
              padding: '1px 5px', lineHeight: '1.4',
            }}>v{version}</span>
          )}
        </div>
        <div style={pptStyles.meta}>{slides} slides · PowerPoint Presentation{version && version > 1 ? ` · Revision ${version}` : ''}</div>
      </div>
      <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
        {onRefine && (
          <button
            onClick={onRefine}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '5px',
              padding: '7px 12px', background: 'transparent', color: 'var(--primary)',
              borderRadius: 'var(--radius-md)', fontSize: '12px', fontWeight: 600,
              border: '1px solid var(--primary)', cursor: 'pointer',
              transition: 'background 0.15s',
            }}
            title="Revise this presentation with a follow-up prompt"
          >
            <Edit2 size={12} />
            Refine
          </button>
        )}
        <a
          href={downloadUrl}
          download={filename || "Presentation.pptx"}
          style={pptStyles.dlBtn}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Download size={14} />
          Download
        </a>
      </div>
    </div>
  );
}

// ── Summary Card ──
function SummaryCard({ filename, downloadUrl }) {
  return (
    <div style={pptStyles.card}>
      <div style={{ ...pptStyles.icon, background: 'rgba(52, 211, 153, 0.1)' }}>
        <BookOpen size={24} color="#34d399" />
      </div>
      <div style={pptStyles.info}>
        <div style={pptStyles.title}>Executive Summary</div>
        <div style={pptStyles.meta}>{filename} · Word Document</div>
      </div>
      {downloadUrl && (
        <a href={downloadUrl} download={filename || "Summary.docx"} style={{ ...pptStyles.dlBtn, background: '#34d399' }}>
          <Download size={14} />
          Download
        </a>
      )}
    </div>
  );
}

// ── Source Side Panel with Citation Highlighting ──
function SourcePanel({ source, onClose, apiUrl }) {
  if (!source) return null;
  const token = getToken();
  const downloadHref = source.doc_id
    ? `${apiUrl}/api/agent/download/doc/${source.doc_id}?token=${encodeURIComponent(token || '')}`
    : null;
  const isPDF = source.document?.toLowerCase().endsWith('.pdf');
  // Use #search= for native browser PDF text highlighting
  const searchPhrase = source.excerpt?.split(/[.!?]+/).filter(s => s.trim().length > 10)?.[0]?.trim().slice(0, 80) || '';
  const pdfViewUrl = downloadHref && isPDF
    ? `${downloadHref}#page=${source.page || 1}${searchPhrase ? '&search=' + encodeURIComponent(searchPhrase) : ''}`
    : null;

  // Highlight matching keywords from excerpt in the displayed text
  const highlightExcerpt = (text) => {
    if (!text) return '';
    // Find sentences/phrases to highlight (first 3 significant phrases)
    const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 20).slice(0, 3);
    let html = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    for (const sent of sentences) {
      const escaped = sent.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      if (escaped.length > 15) {
        html = html.replace(
          new RegExp(`(${escaped.slice(0, 60)})`, 'gi'),
          '<mark style="background:rgba(74,139,255,0.2);color:inherit;padding:1px 2px;border-radius:2px">$1</mark>'
        );
      }
    }
    return html;
  };

  return (
    <div style={panelStyles.overlay} onClick={onClose}>
      <div style={panelStyles.panel} onClick={e => e.stopPropagation()}>
        <div style={panelStyles.header}>
          <div style={panelStyles.headerLeft}>
            <FileText size={16} color="var(--primary)" />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={panelStyles.filename}>{source.document}</span>
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                {source.page && <span style={panelStyles.page}>Page {source.page}</span>}
                {source.clause && source.clause !== "Unknown" && (
                  <span style={{ ...panelStyles.page, background: 'rgba(255,69,0,0.1)', color: 'var(--accent-red)' }}>
                    {source.clause}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button onClick={onClose} style={panelStyles.closeBtn}><X size={16} /></button>
        </div>

        {/* PDF Preview */}
        {pdfViewUrl && (
          <div style={{ flex: '0 0 auto', borderBottom: '1px solid var(--border)' }}>
            <iframe
              src={pdfViewUrl}
              title="PDF Preview"
              style={{
                width: '100%', height: '300px', border: 'none',
                background: 'var(--bg-surface)',
              }}
            />
          </div>
        )}

        {/* Highlighted Excerpt */}
        <div style={panelStyles.excerptSection}>
          <div style={panelStyles.excerptLabel}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Referenced Excerpt
            </span>
          </div>
          <div
            style={panelStyles.excerpt}
            dangerouslySetInnerHTML={{ __html: highlightExcerpt(source.excerpt) }}
          />
        </div>

        {downloadHref && (
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)' }}>
            <a href={downloadHref} download style={panelStyles.downloadBtn} target="_blank" rel="noopener noreferrer">
              <Download size={14} />
              Download full document
            </a>
            {isPDF && source.page && (
              <a href={pdfViewUrl} target="_blank" rel="noopener noreferrer" style={{ ...panelStyles.downloadBtn, background: 'transparent', color: 'var(--primary)', border: '1px solid var(--primary)', marginTop: '6px' }}>
                <ExternalLink size={14} />
                Open at page {source.page}
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}


export default function Chat() {
  const [sessions, setSessions] = useState(loadSessions());
  const [activeSessionId, setActiveSessionId] = useState(
    () => localStorage.getItem(ACTIVE_KEY) || null
  );
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isProcessingBg, setIsProcessingBg] = useState(false); // Separate flag for custom bg actions
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null); // for side panel
  const [isHindi, setIsHindi] = useState(false); // Hindi language toggle
  const [selectedFiles, setSelectedFiles] = useState([]); // VLM image attachments
  const [attachedDocs, setAttachedDocs] = useState([]);   // Document attachments for chat
  const [isPollingDrawing, setIsPollingDrawing] = useState(false);

  // ── Workstream A: Persistent Draft State ──
  // Unified draft model: text + all file attachments + upload-in-progress flag.
  // This prevents race conditions when Enter is pressed mid-upload.
  const [draft, setDraft] = useState({ text: '', files: [], isUploading: false });
  
  // Phase 5: Multi-document context selection
  const [documents, setDocuments] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [showDocSelector, setShowDocSelector] = useState(false);

  // Phase C2: Upload wizard state
  const [uploadQueue, setUploadQueue] = useState([]); // files pending metadata
  const [uploadJobs, setUploadJobs] = useState([]);   // active/completed jobs
  const [showUploadWizard, setShowUploadWizard] = useState(false);

  // PPT version history per session: { [sessionId]: { topic, version, slidesJson } }
  const [pptHistory, setPptHistory] = useState({});

  const navigate = useNavigate();


  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const streamRefs = useRef({}); // { [sessionId]: abortFn } — supports concurrent SSE across tabs
  const fileInputRef = useRef(null);
  const activeSessionIdRef = useRef(activeSessionId);

  const switchSession = (id) => {
    // Workstream J: Save current messages to departing session before switching
    const departingId = activeSessionIdRef.current;
    if (departingId && departingId !== id) {
      setSessions(prev => {
        const u = prev.map(s => s.id === departingId ? { ...s, messages: messages, updatedAt: Date.now() } : s);
        saveSessions(u);
        return u;
      });
    }
    setActiveSessionId(id);
    activeSessionIdRef.current = id;
  };

  const token = getToken();
  const user = token ? (getUser() || decodeToken(token)) : null;
  const isSuperAdmin = user?.role === 'super_admin';
  const apiUrl = getApiUrl('');
  const { theme, toggleTheme } = useTheme();

  const [notification, setNotification] = useState(null); // { message: string, type: 'success'|'error' }
  const notificationTimeoutRef = useRef(null);

  // Workstream: Floating Notification Sound
  const playNotificationSound = useCallback(() => {
    try {
      const audio = new Audio("https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3");
      audio.volume = 0.5;
      audio.play();
    } catch (e) { console.error("Sound play failed", e); }
  }, []);

  const showNotification = useCallback((message, type = 'success') => {
    if (notificationTimeoutRef.current) clearTimeout(notificationTimeoutRef.current);
    setNotification({ message, type });
    playNotificationSound();
    notificationTimeoutRef.current = setTimeout(() => setNotification(null), 5000);
  }, [playNotificationSound]);

  useEffect(() => {
    // Fetch available documents for the context selector
    api.get('/documents')
      .then(({ data }) => setDocuments(data.documents || []))
      .catch(err => console.error("Failed to load documents", err));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Keep activeSessionIdRef in sync
  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  // Abort active stream when switching sessions (session isolation).
  // IMPORTANT: only abort if we are leaving an *existing* session (prev activeSessionId
  // is truthy). When creating the very first session from null we must NOT abort
  // the stream that handleSend just started — otherwise the first message is
  // silently dropped.
  useEffect(() => {
    return () => {
      // activeSessionId captured here is the value from the PREVIOUS render.
      const prevSessId = activeSessionId;
      if (prevSessId && streamRefs.current[prevSessId]) {
        try { streamRefs.current[prevSessId](); } catch (_) {}
        delete streamRefs.current[prevSessId];
      }
    };
  }, [activeSessionId]);

  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem(ACTIVE_KEY, activeSessionId);
      const sess = sessions.find(s => s.id === activeSessionId);
      const loaded = sess?.messages || [];
      // Recover from stale streaming state (e.g. page closed mid-stream)
      const cleaned = loaded.map(m =>
        m.streaming ? { ...m, streaming: false, isError: m.content ? false : true } : m
      );
      setMessages(cleaned);
    } else {
      setMessages([]);
    }
  }, [activeSessionId]);

  const persistMessages = useCallback((msgs, sessId) => {
    // Workstream J: sessId is REQUIRED — never fall back to activeSessionId
    // to prevent cross-session writes during concurrent streams.
    const sid = sessId;
    if (!sid) {
      console.warn('[AGRA] persistMessages called without sessId — skipping');
      return;
    }
    setSessions(prev => {
      const exists = prev.find(s => s.id === sid);
      let updated;
      if (exists) {
        updated = prev.map(s =>
          s.id === sid ? { ...s, messages: msgs, updatedAt: Date.now() } : s
        );
      } else {
        // If it doesn't exist (race condition), create it
        const newSess = { 
          id: sid, 
          title: msgs.find(m => m.role === 'user')?.content?.slice(0, 50) || 'New Chat',
          messages: msgs, 
          createdAt: Date.now(), 
          updatedAt: Date.now() 
        };
        updated = [newSess, ...prev];
      }
      saveSessions(updated);
      return updated;
    });
  }, []);

  const createNewChat = () => {
    const id = newSessionId();
    const sess = { id, title: 'New Chat', messages: [], createdAt: Date.now(), updatedAt: Date.now() };
    setSessions(prev => { const u = [sess, ...prev]; saveSessions(u); return u; });
    switchSession(id);
    setMessages([]);
    setInput('');
    inputRef.current?.focus();
  };

  const deleteSession = (id, e) => {
    e.stopPropagation();
    if (!isSuperAdmin) return;
    setSessions(prev => { const u = prev.filter(s => s.id !== id); saveSessions(u); return u; });
    if (activeSessionId === id) { switchSession(null); setMessages([]); }
  };

  // ── Handle generation intents from chat ──
  const handleIntent = async (intent, intentParams, originalQuestion) => {
    const { type, doc_ids, doc_id, topic, num_slides, num_mcq, num_short_answer, summary_type } = intentParams;
    const authHeader = { Authorization: `Bearer ${token}` };

    try {
      if (type === 'ppt') {
        // ── BACKGROUND PPT GENERATION ──
        // Immediately return a placeholder so the user can keep chatting
        const sessHistory = pptHistory[activeSessionIdRef.current];
        const isRevision = sessHistory && sessHistory.topic?.toLowerCase() === topic?.toLowerCase();
        const version = isRevision ? (sessHistory.version || 1) + 1 : 1;
        const prevSlides = isRevision ? sessHistory.slidesJson : null;
        const revisionPrompt = isRevision ? originalQuestion : null;
        const capturedSessId = activeSessionIdRef.current;

        const requestBody = {
          topic,
          num_slides: num_slides || 10,
          doc_ids,
          version,
          ...(revisionPrompt && { revision_prompt: revisionPrompt }),
          ...(prevSlides && { previous_slides_json: prevSlides }),
        };

        // Fire PPT generation in background (non-blocking)
        setIsProcessingBg(true);
        (async () => {
          try {
            const res = await fetch(getApiUrl('/api/agent/generate/ppt'), {
              method: 'POST',
              headers: { ...authHeader, 'Content-Type': 'application/json' },
              body: JSON.stringify(requestBody),
            });
            if (!res.ok) throw new Error(`PPT generation failed: ${res.status}`);

            const slidesJson = res.headers.get('X-Slides-JSON') || null;
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const versionLabel = version > 1 ? ` v${version}` : '';
            const filename = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1]
              || `AGRA_${topic.slice(0, 30)}${version > 1 ? '_v' + version : ''}.pptx`;

            setPptHistory(prev => ({
              ...prev,
              [capturedSessId]: { topic, version, slidesJson },
            }));

            const updateMsgsForSess = (updater) => {
              if (activeSessionIdRef.current === capturedSessId) {
                setMessages(prev => {
                  const copy = updater([...prev]);
                  persistMessages(copy, capturedSessId);
                  return copy;
                });
              } else {
                setSessions(prevSessions => {
                  const updatedSessions = prevSessions.map(sess => {
                    if (sess.id === capturedSessId) {
                      const copy = updater([...(sess.messages || [])]);
                      return { ...sess, messages: copy, updatedAt: Date.now() };
                    }
                    return sess;
                  });
                  saveSessions(updatedSessions);
                  return updatedSessions;
                });
              }
            };

            // Append finished PPT as a new message (even if user switched sessions)
            updateMsgsForSess(copy => {
              const placeholderIdx = copy.findIndex(m => m._pptJobId === capturedSessId + topic);
              if (placeholderIdx >= 0) {
                copy[placeholderIdx] = {
                  role: 'assistant',
                  content: `✅ Your PowerPoint presentation${versionLabel} on **${topic}** is ready!${version > 1 ? '\n\n_This is a revised version based on your feedback._' : ''}`,
                  ppt: { filename, downloadUrl: url, topic, slides: num_slides || 10, version },
                  sources: [],
                  timestamp: Date.now(),
                  streaming: false,
                };
              } else {
                copy.push({
                  role: 'assistant',
                  content: `✅ Your PowerPoint presentation${versionLabel} on **${topic}** is ready!`,
                  ppt: { filename, downloadUrl: url, topic, slides: num_slides || 10, version },
                  sources: [],
                  timestamp: Date.now(),
                });
              }
              showNotification(`Presentation on "${topic}" is ready!`, 'success');
              return copy;
            });
          } catch (err) {
            const updateMsgsForSess = (updater) => {
              if (activeSessionIdRef.current === capturedSessId) {
                setMessages(prev => {
                  const copy = updater([...prev]);
                  persistMessages(copy, capturedSessId);
                  return copy;
                });
              } else {
                setSessions(prevSessions => {
                  const updatedSessions = prevSessions.map(sess => {
                    if (sess.id === capturedSessId) {
                      const copy = updater([...(sess.messages || [])]);
                      return { ...sess, messages: copy, updatedAt: Date.now() };
                    }
                    return sess;
                  });
                  saveSessions(updatedSessions);
                  return updatedSessions;
                });
              }
            };

            updateMsgsForSess(copy => {
              const placeholderIdx = copy.findIndex(m => m._pptJobId === capturedSessId + topic);
              if (placeholderIdx >= 0) {
                copy[placeholderIdx] = {
                  ...copy[placeholderIdx],
                  content: `❌ PPT generation failed: ${err.message}`,
                  streaming: false, isError: true,
                };
              }
              return copy;
            });
          } finally {
            setIsProcessingBg(false);
          }
        })();

        // Return a placeholder immediately so the user can keep chatting
        return {
          role: 'assistant',
          content: `⏳ Generating PowerPoint on **${topic}** in the background... You can continue chatting. I'll notify you when it's ready.`,
          sources: [],
          timestamp: Date.now(),
          streaming: true,
          _pptJobId: capturedSessId + topic,
        };
      }

      if (type === 'quiz') {
        const res = await fetch(getApiUrl('/api/agent/generate/quiz'), {
          method: 'POST',
          headers: { ...authHeader, 'Content-Type': 'application/json' },
          body: JSON.stringify({ doc_id, num_mcq: num_mcq || 5, num_short_answer: num_short_answer || 3 }),
        });
        if (!res.ok) throw new Error(`Quiz generation failed: ${res.status}`);
        const data = await res.json();
        return {
          role: 'assistant',
          content: 'Here is your knowledge quiz:',
          quiz: data.quiz,
          sources: [],
          timestamp: Date.now(),
        };
      }
      showNotification('Quiz is ready!', 'success');
      if (type === 'summary' || type === 'draft_sotr' || type === 'tech_review') {
        // Stream the document
        return null; // handled via stream separately
      }
    } catch (err) {
      return {
        role: 'assistant',
        content: `Sorry, I couldn't generate the ${type}: ${err.message}`,
        sources: [],
        timestamp: Date.now(),
        isError: true,
      };
    }
  };

  // ── Stream Document via SSE ──
  const streamDocument = (intentType, intentParams, sessId, updateMsgs) => {
    const { doc_id, summary_type, target_audience } = intentParams;
    let accumulated = '';
    let docDownloadUrl = null;

    let endpoint = '/api/agent/generate/summary';
    let payload = { doc_id, summary_type: summary_type || 'executive' };

    if (intentType === 'draft_sotr') {
      endpoint = '/api/agent/generate/sotr';
      payload = { doc_id };
    } else if (intentType === 'tech_review') {
      endpoint = '/api/agent/generate/tech-review';
      payload = { doc_id, target_audience: target_audience || 'shipyard' };
    }

    const abort = connectStream(
      getApiUrl(endpoint),
      payload,
      (data) => {
        if (data.token) {
          accumulated += data.token;
          updateMsgs(accumulated, null);
        }
      },
      (data) => {
        docDownloadUrl = data.download_url || null;
        updateMsgs(accumulated, docDownloadUrl);
        setIsStreaming(false);
        showNotification('Document generation complete.', 'success');
      },
      (err) => {
        updateMsgs(accumulated || `Error: ${err.message}`, null);
        setIsStreaming(false);
      }
    );
    return abort;
  };

  // ── Branch-isolated bid comparison via SSE ──
  const runBranchComparison = async (intentParams, question, sessId) => {
    const { comparable_tenders, problem_statement: validatedPs, available } = intentParams;

    if (!available || !comparable_tenders?.length) {
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          content: 'I could not find at least two bid documents sharing the same tender. Please upload bids with matching **problem_statement** metadata.',
          streaming: false,
        };
        persistMessages(copy, sessId);
        return copy;
      });
      return;
    }

    const tender = validatedPs
      ? comparable_tenders.find(t => t.problem_statement === validatedPs)
      : comparable_tenders[0];

    if (!tender) {
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          content: 'Could not locate a comparable tender to evaluate.',
          streaming: false,
        };
        persistMessages(copy, sessId);
        return copy;
      });
      return;
    }

    const bidder_keys = tender.bidder_keys;
    const problem_statement = tender.problem_statement;

    setMessages(prev => {
      const copy = [...prev];
      copy[copy.length - 1] = {
        ...copy[copy.length - 1],
        content: `Starting branch-isolated comparison for **${problem_statement}**…\n\nBidders: ${bidder_keys.join(', ')}`,
        streaming: true,
      };
      return copy;
    });

    try {
      const resp = await fetch(getApiUrl('/api/agent/compare/bids/branch'), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          bidder_keys,
          problem_statement,
          standards: ['ICG_TECH_SOTR', 'GENERIC_REQS', 'ISO_9001'],
          focus: question,
        }),
      });
      if (!resp.ok) throw new Error(`Branch comparison failed: ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalData = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;
            try {
              const evt = JSON.parse(dataStr);
              if (evt.stage === 'evaluating') {
                setMessages(prev => {
                  const copy = [...prev];
                  copy[copy.length - 1] = {
                    ...copy[copy.length - 1],
                    content: `**Branch Comparison in progress…**\n\nEvaluating ${evt.bidder_key} against ${evt.standard_id} (${evt.progress}%)`,
                    streaming: true,
                  };
                  return copy;
                });
              }
              if (evt.stage === 'done') {
                finalData = evt;
              }
            } catch (e) {
              console.error('Branch SSE parse error', e, dataStr);
            }
          }
        }
      }

      if (finalData) {
        setMessages(prev => {
          const copy = [...prev];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content: '',
            streaming: false,
            comparison: finalData,
          };
          persistMessages(copy, sessId);
          return copy;
        });
      } else {
        setMessages(prev => {
          const copy = [...prev];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content: 'Comparison completed but no structured data was returned.',
            streaming: false,
          };
          persistMessages(copy, sessId);
          return copy;
        });
      }
    } catch (err) {
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          content: `Branch comparison error: ${err.message}`,
          streaming: false,
          isError: true,
        };
        persistMessages(copy, sessId);
        return copy;
      });
    }
  };

  // Derive streaming state from current session's last message to allow multi-tasking
  const isSessionStreaming = messages.length > 0 && messages[messages.length - 1].streaming === true;

  // ── Timeout fallback: auto-recover sessions stuck in streaming state (90s) ──
  useEffect(() => {
    if (!isSessionStreaming || !activeSessionId) return;
    const sessId = activeSessionId;
    const timeout = setTimeout(() => {
      if (streamRefs.current[sessId]) {
        try { streamRefs.current[sessId](); } catch (_) {}
        delete streamRefs.current[sessId];
      }
      setMessages(prev => {
        if (!prev.length || !prev[prev.length - 1].streaming) return prev;
        const copy = [...prev];
        const last = copy[copy.length - 1];
        copy[copy.length - 1] = {
          ...last,
          content: last.content || '⚠️ Response timed out. The server may be busy processing another request. Please try again.',
          streaming: false,
          isError: !last.content,
        };
        persistMessages(copy, sessId);
        return copy;
      });
      setIsStreaming(false);
    }, 90000);
    return () => clearTimeout(timeout);
  }, [isSessionStreaming, activeSessionId]);

  const uploadDocAndGetId = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
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
    let docId = null;
    while (true) {
      const { value, done } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (!dataStr) continue;
            try {
              const data = JSON.parse(dataStr);
              if (data.stage === 'done') docId = data.doc_id;
              if (data.stage === 'error') throw new Error(data.error || 'Upload failed');
            } catch (e) {
              if (e.message !== 'Upload failed') console.error('Upload SSE parse error', e);
            }
          }
        }
      }
      if (done) break;
    }
    return docId;
  };

  const handleSend = async () => {
    const question = input.trim();
    if ((!question && selectedFiles.length === 0 && attachedDocs.length === 0) || isSessionStreaming) return;

    // ── Workstream A: Atomic snapshot of draft state ──
    // Snapshot current files before clearing so nothing is lost on re-render.
    const snapshotImages = [...selectedFiles];
    const snapshotDocs = [...attachedDocs];
    const snapshotText = question;

    // Build file chip metadata for persistent display in user bubble
    const fileChips = [
      ...snapshotImages.map(f => ({ name: f.name, type: 'image', preview: URL.createObjectURL(f) })),
      ...snapshotDocs.map(f => ({ name: f.name, type: 'document', preview: null })),
    ];

    const userMsg = {
      role: 'user',
      content: snapshotText,
      timestamp: Date.now(),
      image: snapshotImages.length > 0 ? URL.createObjectURL(snapshotImages[0]) : null,
      fileChips, // Workstream A: persisted file metadata for bubble rendering
    };
    const aiMsg = { role: 'assistant', content: '', sources: [], timestamp: Date.now(), streaming: true };
    const updatedMsgs = [...messages, userMsg, aiMsg];

    // Atomically clear all draft state
    setMessages(updatedMsgs);
    setInput('');
    setSelectedFiles([]);
    setAttachedDocs([]);
    setDraft({ text: '', files: [], isUploading: false });
    setIsStreaming(true);

    // Ensure session exists
    let sessId = activeSessionId;
    if (!sessId) {
      const id = newSessionId();
      const sess = { id, title: question.slice(0, 50) || 'Image Analysis', messages: updatedMsgs, createdAt: Date.now(), updatedAt: Date.now() };
      setSessions(prev => { const u = [sess, ...prev]; saveSessions(u); return u; });
      switchSession(id);
      sessId = id;
    } else {
      setSessions(prev => {
        const u = prev.map(s => s.id === sessId
          ? { ...s, title: s.title === 'New Chat' ? (question.slice(0, 50) || 'Image Analysis') : s.title, messages: updatedMsgs, updatedAt: Date.now() }
          : s
        );
        saveSessions(u);
        return u;
      });
    }

    if (snapshotImages.length > 0) {
      // VLM Flow — use the first image file from the atomic snapshot
      const imgToUpload = snapshotImages[0];

      const formData = new FormData();
      formData.append('image', imgToUpload);
      formData.append('prompt', question);

      let accumulatedText = '';

      // Abort any existing VLM stream for this session
      if (streamRefs.current[sessId]) {
        try { streamRefs.current[sessId](); } catch (_) {}
        delete streamRefs.current[sessId];
      }
      
      try {
        const ctrl = new AbortController();
        streamRefs.current[sessId] = () => ctrl.abort();

        const res = await fetch(getApiUrl('/api/agent/vlm/analyze'), {
          signal: ctrl.signal,
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        
        if (!res.ok) throw new Error(`VLM request failed: ${res.status}`);
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        
        while (true) {
          const { value, done } = await reader.read();
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const dataStr = line.slice(6).trim();
                if (!dataStr) continue;
                try {
                  const data = JSON.parse(dataStr);
                  if (data.token) {
                    accumulatedText += data.token;
                    setMessages(prev => {
                      if (activeSessionIdRef.current !== sessId) return prev;
                      const copy = [...prev];
                      copy[copy.length - 1] = { ...copy[copy.length - 1], content: accumulatedText };
                      return copy;
                    });
                  }
                  if (data.done) {
                    if (activeSessionIdRef.current === sessId) {
                      setIsStreaming(false);
                      setMessages(prev => {
                        const copy = [...prev];
                        copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false };
                        persistMessages(copy, sessId);
                        return copy;
                      });
                    }
                    delete streamRefs.current[sessId];
                    return;
                  }
                  if (data.error) {
                    throw new Error(data.error);
                  }
                } catch (e) {
                  console.error("VLM Stream Parse Error:", e, dataStr);
                }
              }
            }
          }
          if (done) break;
        }
      } catch (err) {
         if (activeSessionIdRef.current === sessId) {
           setIsStreaming(false);
           setMessages(prev => {
             const copy = [...prev];
             copy[copy.length - 1] = { ...copy[copy.length - 1], content: accumulatedText || `Error: ${err.message}`, streaming: false, isError: true };
             return copy;
           });
         }
         delete streamRefs.current[sessId];
      }
      return;
    }

    // Upload any attached documents and collect doc_ids for context
    // Workstream A: Use snapshotDocs from atomic draft snapshot instead of live state
    let uploadedDocIds = [];
    if (snapshotDocs.length > 0) {
      setDraft(prev => ({ ...prev, isUploading: true }));
      setMessages(prev => [...prev, { role: 'system', content: `Uploading ${snapshotDocs.length} document(s)...`, timestamp: Date.now(), isToast: true }]);
      for (const file of snapshotDocs) {
        try {
          const docId = await uploadDocAndGetId(file);
          if (docId) uploadedDocIds.push(docId);
        } catch (err) {
          setMessages(prev => [...prev, { role: 'system', content: `⚠️ Failed to upload ${file.name}: ${err.message}`, timestamp: Date.now(), isToast: true }]);
        }
      }
      setDraft(prev => ({ ...prev, isUploading: false }));
      // Remove the uploading toast
      setMessages(prev => prev.filter(m => !(m.isToast && m.content.includes('Uploading'))));
    }

    // Workstream I: Clean history — exclude system/toast/error/streaming, truncate to 500 chars,
    // send only the 10 most recent completed user+assistant turns for reliable context.
    const history = messages
      .filter(m =>
        (m.role === 'user' || m.role === 'assistant') &&
        !m.isToast &&
        !m.isError &&
        !m.streaming &&
        m.content &&
        m.content.trim().length > 0
      )
      .slice(-10)
      .map(m => ({
        role: m.role,
        content: m.content.length > 500 ? m.content.slice(0, 500) + '…' : m.content,
      }));

    let accumulatedText = '';

    const chatPayload = { question, history, session_id: sessId };
    const allDocIds = [...new Set([...selectedDocIds, ...uploadedDocIds])];
    if (allDocIds.length > 0) {
      chatPayload.doc_ids = allDocIds;
    }

    // Abort any existing stream for this session before starting a new one
    if (streamRefs.current[sessId]) {
      try { streamRefs.current[sessId](); } catch (_) {}
      delete streamRefs.current[sessId];
    }

    streamRefs.current[sessId] = connectStream(
      getApiUrl('/api/agent/chat'),
      chatPayload,
      // onToken — guarded with session ID
      (data) => {
        if (activeSessionIdRef.current !== sessId) return; // session isolation guard
        if (data.replace_all !== undefined) {
          accumulatedText = data.replace_all;
          setMessages(prev => {
            if (!prev || prev.length === 0) return prev;
            const copy = [...prev];
            copy[copy.length - 1] = { ...copy[copy.length - 1], content: accumulatedText };
            return copy;
          });
        } else if (data.token) {
          accumulatedText += data.token;
          setMessages(prev => {
            if (!prev || prev.length === 0) return prev;
            const copy = [...prev];
            copy[copy.length - 1] = { ...copy[copy.length - 1], content: accumulatedText };
            return copy;
          });
        }
      },
      async (data) => {
        // Workstream J: Persist to original session even if user switched away
        const isActive = activeSessionIdRef.current === sessId;
        // Check for intent signal
        if (data.intent) {
          const intentType = data.intent;
          const intentParams = data.intent_params || {};

          if (intentType === 'summary' || intentType === 'draft_sotr' || intentType === 'tech_review') {
            // Replace placeholder with header, then stream
            setMessages(prev => {
              const copy = [...prev];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                content: '',
                streaming: true,
                summaryHeader: true, // We reuse this flag for UI layout
              };
              return copy;
            });

            streamRefs.current[sessId] = streamDocument(
              intentType,
              intentParams,
              sessId,
              (text, downloadUrl) => {
                setMessages(prev => {
                  const copy = [...prev];
                  const last = copy[copy.length - 1];
                  copy[copy.length - 1] = {
                    ...last,
                    content: text,
                    streaming: !downloadUrl,
                    summary: downloadUrl ? { downloadUrl } : last.summary, // reuse summary obj for download card
                  };
                  if (!downloadUrl) return copy;
                  // persist final
                  persistMessages(copy, sessId);
                  return copy;
                });
              }
            );
            return;
          }

          if (intentType === 'bid_compare') {
            setIsStreaming(false);
            await runBranchComparison(intentParams, question, sessId);
            return;
          }

          // Workstream E: Compliance intent — render inline ComplianceCard
          if (intentType === 'compliance') {
            setIsStreaming(false);
            setMessages(prev => {
              const copy = [...prev];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                content: 'Running compliance analysis…',
                streaming: false,
                complianceIntent: intentParams, // Signals ComplianceCard to render
              };
              persistMessages(copy, sessId);
              return copy;
            });
            delete streamRefs.current[sessId];
            return;
          }

          // Workstream K/M: Drawing analysis intent — auto-trigger VLM extraction from chat
          if (intentType === 'drawing_extract') {
            setIsStreaming(false);
            const pdfFile = snapshotDocs.find(f => f.type === 'application/pdf');
            if (snapshotImages.length > 0 || pdfFile) {
              // Re-set selectedFiles for handleDrawingExtract (it reads from state)
              if (snapshotImages.length > 0) setSelectedFiles(snapshotImages);
              else if (pdfFile) setSelectedFiles([pdfFile]);
              
              // Small delay to let state settle, then trigger extraction
              setTimeout(() => handleDrawingExtract(), 100);
            } else {
              // No image/PDF attached — guide the user
              setMessages(prev => {
                const copy = [...prev];
                copy[copy.length - 1] = {
                  ...copy[copy.length - 1],
                  content: '🏗️ I detected you want to analyze a drawing, but no image or PDF blueprint is attached.\n\nPlease:\n1. Click the 📎 attachment button\n2. Select an engineering drawing (PNG, JPG) or a PDF blueprint\n3. Then type "analyze this drawing" again\n\nI\'ll run the Vision-Language Model to extract dimensions, tolerances, materials, and equipment tags.',
                  streaming: false,
                };
                persistMessages(copy, sessId);
                return copy;
              });
              delete streamRefs.current[sessId];
            }
            return;
          }

          // PPT or Quiz — call generation API
          setMessages(prev => {
            const copy = [...prev];
            copy[copy.length - 1] = { ...copy[copy.length - 1], content: 'Generating…', streaming: true };
            return copy;
          });

          const result = await handleIntent(intentType, intentParams, question);
          setIsStreaming(false);

          setMessages(prev => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              ...(result || { role: 'assistant', content: 'Done.', sources: [] }),
              streaming: false,
            };
            persistMessages(copy, sessId);
            return copy;
          });
          delete streamRefs.current[sessId];
          return;
        }

        // Normal Q&A done
        if (isActive) setIsStreaming(false);
        const finalText = accumulatedText;
        if (isActive) {
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = {
              ...last,
              content: finalText || last?.content || '',
              sources: data?.sources || [],
              confidence_score: data?.confidence_score,
              streaming: false,
            };
            persistMessages(copy, sessId);
            return copy;
          });
        } else {
          // Workstream J: User switched away — persist to the original session directly
          setSessions(prev => {
            const u = prev.map(s => {
              if (s.id !== sessId) return s;
              const msgs = [...(s.messages || [])];
              if (msgs.length > 0 && msgs[msgs.length - 1].streaming) {
                msgs[msgs.length - 1] = {
                  ...msgs[msgs.length - 1],
                  content: finalText || msgs[msgs.length - 1].content || '',
                  sources: data?.sources || [],
                  confidence_score: data?.confidence_score,
                  streaming: false,
                };
              }
              return { ...s, messages: msgs, updatedAt: Date.now() };
            });
            saveSessions(u);
            return u;
          });
        }
        delete streamRefs.current[sessId];
      },
      // onError — guarded (always persists to prevent frozen sessions)
      (err) => {
        if (activeSessionIdRef.current !== sessId) {
          // Even if session switched, update the original session's data so it doesn't freeze
          setSessions(prevSessions => {
            const updatedSessions = prevSessions.map(sess => {
              if (sess.id === sessId) {
                const msgs = [...(sess.messages || [])];
                if (msgs.length > 0 && msgs[msgs.length - 1].streaming) {
                  msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: msgs[msgs.length - 1].content || `Error: ${err.message}`, streaming: false, isError: true };
                }
                return { ...sess, messages: msgs, updatedAt: Date.now() };
              }
              return sess;
            });
            saveSessions(updatedSessions);
            return updatedSessions;
          });
          delete streamRefs.current[sessId];
          return;
        }
        setIsStreaming(false);
        setMessages(prev => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = {
            ...last,
            content: accumulatedText || `Error: ${err.message}`,
            streaming: false,
            isError: true,
          };
          persistMessages(copy, sessId);
          return copy;
        });
        delete streamRefs.current[sessId];
      }
    );
  };

  // ── Workstream A: Clean Enter key handling ──
  // Block submission while draft is uploading files to prevent partial sends.
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (draft.isUploading) return; // Block send while files are uploading
      handleSend();
    }
  };

  const handleFileAttach = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    const images = [];
    const docs = [];
    const rejected = [];
    for (const file of files) {
      if (file.type.startsWith('image/')) {
        images.push(file);
      } else if (['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'].includes(file.type)) {
        docs.push(file);
      } else {
        rejected.push(file.name);
      }
    }

    if (images.length > 0) {
      setSelectedFiles(prev => [...prev, ...images]);
    }
    if (docs.length > 0) {
      setAttachedDocs(prev => [...prev, ...docs]);
    }
    if (rejected.length > 0) {
      setMessages(prev => [...prev, {
        role: 'system',
        content: `⚠️ Unsupported files (${rejected.join(', ')}) — only PDF, DOCX, DOC and TXT are accepted.`,
        timestamp: Date.now(),
        isToast: true,
      }]);
      setTimeout(() => {
        setMessages(prevMsgs => prevMsgs.filter(m => !(m.isToast && m.content.includes(rejected[0]))));
      }, 5000);
    }
    e.target.value = '';
  };

  const updateUploadField = (index, field, value) => {
    setUploadQueue(prev => prev.map((item, i) => i === index ? { ...item, [field]: value } : item));
  };

  const removeFromQueue = (index) => {
    setUploadQueue(prev => {
      const next = prev.filter((_, i) => i !== index);
      if (next.length === 0) setShowUploadWizard(false);
      return next;
    });
  };

  const startUploads = async () => {
    if (uploadQueue.length === 0) return;
    setShowUploadWizard(false);

    const sessId = activeSessionIdRef.current || newSessionId();
    if (!activeSessionId) switchSession(sessId);

    for (const item of uploadQueue) {
      const job = {
        id: 'up_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6),
        filename: item.file.name,
        stage: 'uploading',
        progress: 0,
        metadata: { document_type: item.document_type, bidder_key: item.bidder_key, problem_statement: item.problem_statement },
        error: null,
        doc_id: null,
      };
      setUploadJobs(prev => [...prev, job]);

      const formData = new FormData();
      formData.append('file', item.file);
      formData.append('document_type', item.document_type || '');
      formData.append('bidder_key', item.bidder_key || '');
      formData.append('problem_statement', item.problem_statement || '');
      formData.append('auto_extract', 'true');

      try {
        const res = await fetch(getApiUrl('/api/agent/upload'), {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        if (!res.ok) throw new Error(`Upload failed: ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const dataStr = line.slice(6).trim();
                if (!dataStr) continue;
                try {
                  const data = JSON.parse(dataStr);
                  setUploadJobs(prev => prev.map(j => {
                    if (j.id !== job.id) return j;
                    if (data.stage === 'saved') return { ...j, stage: 'saved', progress: 10 };
                    if (data.stage === 'metadata_extraction') return { ...j, stage: 'extracting', progress: 20 };
                    if (data.stage === 'metadata_extracted') return { ...j, stage: 'extracted', progress: 35, metadata: { ...j.metadata, ...data.metadata } };
                    if (data.stage === 'chunking') return { ...j, stage: 'chunking', progress: 50 };
                    if (data.stage === 'embedding') return { ...j, stage: 'embedding', progress: 70 };
                    if (data.stage === 'storing') return { ...j, stage: 'storing', progress: 90 };
                    if (data.stage === 'done') return { ...j, stage: 'done', progress: 100, doc_id: data.doc_id };
                    if (data.stage === 'error') return { ...j, stage: 'error', error: data.error };
                    return j;
                  }));
                } catch (e) {
                  console.error('Upload SSE parse error', e, dataStr);
                }
              }
            }
          }
          if (done) break;
        }
      } catch (err) {
        setUploadJobs(prev => prev.map(j => j.id === job.id ? { ...j, stage: 'error', error: err.message } : j));
      }
    }
    setUploadQueue([]);
  };

  const handleCompare = async () => {
    if (selectedDocIds.length < 2) return;
    setIsProcessingBg(true);
    
    const sessId = activeSessionIdRef.current || newSessionId();
    if (!activeSessionId) {
      switchSession(sessId);
      setSessions(prev => [{ id: sessId, title: "Bid Comparison" }, ...prev]);
    }

    setMessages(prev => [...prev, {
      role: 'user',
      content: 'Please compare the selected bid documents. ' + input,
      timestamp: new Date().toISOString()
    }, {
      role: 'assistant',
      content: 'Starting comparative analysis...',
      streaming: true,
      timestamp: new Date().toISOString()
    }]);

    try {
      const resp = await fetch(getApiUrl('/api/agent/compare/bids'), {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({
          bid_doc_ids: selectedDocIds,
          standard_doc_id: null,
          check_scope: input
        })
      });

      if (!resp.ok) throw new Error("Failed to start comparison");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = '### Cross-Document Comparative Analysis\n\n';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            if (!dataStr) continue;
            try {
              const data = JSON.parse(dataStr);
              if (data.comparison) {
                const comp = data.comparison;
                accumulatedContent += `#### ${comp.parameter}\n`;
                accumulatedContent += `- **Standard**: ${comp.standard_requirement}\n`;
                for (const bid of comp.bids || []) {
                  accumulatedContent += `- **${bid.bidder}**: ${bid.value} *(Compliant: ${bid.compliant})*\n`;
                }
                accumulatedContent += `\n**Analysis**: ${comp.analysis}\n`;
                accumulatedContent += `**Winner**: ${comp.winner}\n\n`;
                
                setMessages(prev => {
                  const copy = [...prev];
                  copy[copy.length - 1] = { ...copy[copy.length - 1], content: accumulatedContent };
                  return copy;
                });
              }
              if (data.done) {
                setMessages(prev => {
                  const copy = [...prev];
                  copy[copy.length - 1] = { 
                    ...copy[copy.length - 1], 
                    streaming: false,
                    summary: data.download_url ? { downloadUrl: data.download_url } : null
                  };
                  return copy;
                });
                break;
              }
            } catch (e) {
              console.error("Parse error", e);
            }
          }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], content: 'Error: ' + err.message, streaming: false, isError: true };
        return copy;
      });
    } finally {
      setIsProcessingBg(false);
      setInput('');
    }
  };

  const handleDrawingExtract = async () => {
    if (selectedFiles.length === 0) return;
    setIsPollingDrawing(true);
    const targetImage = selectedFiles[0];

    // Add temporary message
    const tempUrl = URL.createObjectURL(targetImage);
    setMessages(prev => [...prev, {
      role: 'user',
      content: 'Please extract parameters from this drawing.',
      image: tempUrl,
      timestamp: Date.now(),
    }]);

    try {
      const formData = new FormData();
      formData.append('image', targetImage);
      
      const resp = await fetch(getApiUrl('/api/agent/drawing/extract_parameters'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!resp.ok) throw new Error('Failed to start extraction');
      const { job_id } = await resp.json();
      
      // Poll for completion
      const interval = setInterval(async () => {
        const statusResp = await fetch(getApiUrl(`/api/agent/drawing/jobs/${job_id}`), {
          headers: { Authorization: `Bearer ${token}` }
        });
        const statusData = await statusResp.json();
        if (statusData.status === 'completed') {
          clearInterval(interval);
          setIsPollingDrawing(false);
          setSelectedFiles([]);
          
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: '📐 Drawing parameters extracted successfully.',
            drawingResult: statusData.result_data, // Workstream F: structured rendering
            timestamp: Date.now(),
          }]);
          showNotification('Drawing analysis complete.', 'success');
        } else if (statusData.status === 'failed') {
          clearInterval(interval);
          setIsPollingDrawing(false);
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: 'Failed to extract parameters: ' + statusData.error_message,
            isError: true,
            timestamp: new Date().toISOString()
          }]);
        }
      }, 3000);
      
    } catch (err) {
      setIsPollingDrawing(false);
      console.error(err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Failed to start drawing extraction.',
        isError: true,
        timestamp: new Date().toISOString()
      }]);
    }
  };

  // Citation click handler — attach to document, read data-cite attr
  useEffect(() => {
    const handler = (e) => {
      const chip = e.target.closest('.cite-chip');
      if (!chip) return;
      const citeIdx = parseInt(chip.getAttribute('data-cite'));
      // Find which message this belongs to
      for (const msg of messages) {
        if (msg.sources && msg.sources[citeIdx]) {
          setSelectedSource(msg.sources[citeIdx]);
          break;
        }
      }
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [messages]);

  useEffect(() => () => {
    Object.values(streamRefs.current).forEach(abort => { try { abort(); } catch (_) {} });
    streamRefs.current = {};
  }, []);

  return (
    <div style={styles.layout}>
      {/* ── Sidebar ── */}
      <aside style={{ ...styles.sidebar, width: sidebarCollapsed ? '60px' : '260px', minWidth: sidebarCollapsed ? '60px' : '260px' }}>
        <div style={styles.sidebarHeader}>
          <div style={styles.logoGroup}>
            <div style={styles.logoIcon}><ShieldCheck size={20} color="var(--primary)" /></div>
            {!sidebarCollapsed && (
              <div>
                <div style={styles.logoText}>AGRA</div>
                <div style={styles.logoSub}>Secure Intelligence</div>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '2px' }}>
            <button onClick={toggleTheme} style={styles.collapseBtn} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
              {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </button>
            <button onClick={() => setIsHindi(!isHindi)} style={{...styles.collapseBtn, fontSize: '11px', fontWeight: 'bold'}} title="Toggle Hindi">
              {isHindi ? 'EN' : 'HI'}
            </button>
            <button onClick={() => setSidebarCollapsed(p => !p)} style={styles.collapseBtn} title="Toggle sidebar">
              {sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
          </div>
        </div>

        <button onClick={createNewChat} style={styles.newChatBtn} id="new-chat-btn">
          <Plus size={16} />
          {!sidebarCollapsed && <span>{isHindi ? 'नई चैट' : 'New Chat'}</span>}
        </button>

        {!sidebarCollapsed && (
          <div style={styles.sessionList}>
            {sessions.length === 0 && (
              <div style={styles.emptyState}>
                <MessageSquare size={18} style={{ opacity: 0.3 }} />
                <span>{isHindi ? 'अभी तक कोई बातचीत नहीं' : 'No conversations yet'}</span>
              </div>
            )}
            {sessions.map(sess => (
              <div
                key={sess.id}
                onClick={() => switchSession(sess.id)}
                style={{
                  ...styles.sessionItem,
                  background: activeSessionId === sess.id ? 'rgba(74,139,255,0.08)' : 'transparent',
                  borderLeft: activeSessionId === sess.id ? '2px solid #4a8bff' : '2px solid transparent',
                }}
              >
                <MessageSquare size={13} style={{ flexShrink: 0, opacity: 0.4 }} />
                <span style={styles.sessionTitle}>{sess.title}</span>
                {sess.messages?.[sess.messages.length - 1]?.streaming && (
                  <Loader2 size={12} style={{ marginLeft: 'auto', flexShrink: 0, color: 'var(--primary)', animation: 'spin 1s linear infinite' }} />
                )}
                {isSuperAdmin && (
                  <button onClick={(e) => deleteSession(sess.id, e)} style={styles.sessionDeleteBtn} title="Delete">
                    <X size={12} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        <div style={styles.navSection}>
          <Link to="/compliance" style={styles.navLink}><ShieldCheck size={15} />{!sidebarCollapsed && <span>{isHindi ? 'अनुपालन' : 'Compliance'}</span>}</Link>
          {isSuperAdmin && (
            <a href={getDashboardUrl('/dashboard')} style={styles.navLink}><LayoutDashboard size={15} />{!sidebarCollapsed && <span>{isHindi ? 'डैशबोर्ड' : 'Dashboard'}</span>}</a>
          )}
        </div>

        <div style={styles.sidebarFooter}>
          {!sidebarCollapsed && user && (
            <div style={styles.userInfo}>
              <div style={styles.userAvatar}><User size={13} /></div>
              <span style={styles.userName}>{user.sub || user.username || 'Agent'}</span>
            </div>
          )}
          <button onClick={logout} style={styles.logoutBtn} title="Logout" id="logout-btn">
            <LogOut size={15} />
            {!sidebarCollapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* ── Floating Notification ── */}
      {notification && (
        <div style={{
          position: 'fixed', top: '24px', right: '24px', zIndex: 10000,
          background: notification.type === 'success' ? 'rgba(34,197,94,0.9)' : 'rgba(239,68,68,0.9)',
          backdropFilter: 'blur(12px)', color: '#fff', padding: '12px 20px',
          borderRadius: '12px', boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          display: 'flex', alignItems: 'center', gap: '12px',
          animation: 'slideIn 0.3s ease-out forwards',
          border: '1px solid rgba(255,255,255,0.1)',
        }}>
          {notification.type === 'success' ? <CheckCircle size={18} /> : <AlertTriangle size={18} />}
          <span style={{ fontWeight: 600, fontSize: '14px' }}>{notification.message}</span>
          <button onClick={() => setNotification(null)} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: '4px', marginLeft: '8px', opacity: 0.8 }}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* ── Main Area ── */}
      <main style={styles.main}>
        {messages.length === 0 ? (
          <div style={styles.welcome}>
            <div style={styles.welcomeIcon}><Sparkles size={36} color="var(--primary)" /></div>
            <h1 style={styles.welcomeTitle}>{isHindi ? 'एग्रा इंटेलिजेंस एजेंट' : 'AGRA Intelligence Agent'}</h1>
            <p style={styles.welcomeDesc}>
              {isHindi 
                ? 'प्रश्न पूछें, प्रेजेंटेशन बनाएं, क्विज़ जनरेट करें, या सारांश प्राप्त करें — सब सिस्टम के प्रमाणित दस्तावेज़ों से।'
                : 'Ask questions, generate presentations, create quizzes, or get summaries — all from the system\'s vetted documents.'}
            </p>
            <div style={styles.suggestionsGrid}>
              {[
                { icon: <MessageSquare size={14} />, text: isHindi ? 'SOTR में मुख्य आवश्यकताएं क्या हैं?' : 'What are the key requirements in the SOTR?' },
                { icon: <Presentation size={14} />, text: isHindi ? 'ICG AGRA के बारे में एक PPT बनाएं' : 'Create a PPT about ICG AGRA' },
                { icon: <ClipboardList size={14} />, text: isHindi ? 'अपलोड किए गए दस्तावेज़ से एक क्विज़ जनरेट करें' : 'Generate a quiz from the uploaded document' },
                { icon: <BookOpen size={14} />, text: isHindi ? 'तकनीकी प्रस्ताव का सारांश दें' : 'Summarize the technical proposal' },
                { icon: <FileText size={14} />, text: isHindi ? 'इस दस्तावेज़ से एक SOTR ड्राफ्ट करें' : 'Draft an SOTR from this document' },
                { icon: <AlertTriangle size={14} />, text: isHindi ? 'शिपयार्ड के लिए तकनीकी समीक्षा टिप्पणियां बनाएं' : 'Generate technical review comments for the shipyard' },
              ].map((q, i) => (
                <button
                  key={i}
                  onClick={() => { setInput(q.text); inputRef.current?.focus(); }}
                  style={styles.suggestionCard}
                >
                  <span style={styles.suggestionIcon}>{q.icon}</span>
                  {q.text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={styles.messagesContainer}>
            {messages.map((msg, idx) => (
              <div
                key={idx}
                style={{
                  ...styles.msgRow,
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                {msg.role === 'assistant' && (
                  <div style={styles.aiAvatar}><Bot size={15} color="var(--primary)" /></div>
                )}
                <div style={{
                  ...styles.bubble,
                  ...(msg.role === 'user' ? styles.userBubble : styles.aiBubble),
                  ...(msg.isError ? { borderColor: '#ef4444' } : {}),
                }}>
                  {msg.role === 'assistant' ? (
                    <>
                      {/* Streaming text or markdown content */}
                      {msg.content && (
                        <div
                          className="md-content"
                          dangerouslySetInnerHTML={{
                            __html: renderWithCitations(
                              renderMarkdown(msg.content),
                              msg.sources || [],
                              (src) => setSelectedSource(src)
                            )
                          }}
                        />
                      )}
                      {msg.streaming && <span style={styles.cursor}>▊</span>}

                      {/* PPT Card */}
                      {msg.ppt && !msg.streaming && (
                        <PPTCard
                          filename={msg.ppt.filename}
                          slides={msg.ppt.slides}
                          downloadUrl={msg.ppt.downloadUrl}
                          topic={msg.ppt.topic}
                          version={msg.ppt.version}
                          onRefine={() => {
                            setInput(`Revise the PPT about "${msg.ppt.topic}": `);
                            inputRef.current?.focus();
                          }}
                        />
                      )}

                      {/* Quiz */}
                      {msg.quiz && !msg.streaming && <InlineQuiz quiz={msg.quiz} />}

                      {/* Summary download card */}
                      {msg.summary?.downloadUrl && !msg.streaming && (
                        <SummaryCard
                          filename="Summary Document"
                          downloadUrl={`${getApiUrl(msg.summary.downloadUrl)}?token=${encodeURIComponent(token || '')}`}
                        />
                      )}

                      {/* Branch-isolated Comparison Card */}
                      {msg.comparison && !msg.streaming && (
                        <ComparisonCard data={msg.comparison} />
                      )}

                      {/* Workstream E: Inline Compliance Analysis */}
                      {msg.complianceIntent && !msg.streaming && (
                        <ComplianceCard intentParams={msg.complianceIntent} token={token} />
                      )}

                      {/* Workstream F: Inline Drawing Extraction Results */}
                      {msg.drawingResult && !msg.streaming && (
                        <div style={{ marginTop: '10px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg, 12px)', overflow: 'hidden' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>
                            📐 Drawing Parameters
                          </div>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1px', background: 'var(--border)' }}>
                            {[
                              { label: 'Dimensions', items: msg.drawingResult.dimensions, icon: '📏' },
                              { label: 'Tolerances', items: msg.drawingResult.tolerances, icon: '🎯' },
                              { label: 'Materials', items: msg.drawingResult.materials, icon: '🔩' },
                              { label: 'Equipment Tags', items: msg.drawingResult.equipment_tags, icon: '🏷️' },
                            ].map((group, gi) => (
                              <div key={gi} style={{ padding: '10px 12px', background: 'var(--bg-card)' }}>
                                <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                                  {group.icon} {group.label}
                                </div>
                                {group.items?.length > 0 ? (
                                  <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                                    {group.items.map((item, ii) => <li key={ii}>{item}</li>)}
                                  </ul>
                                ) : (
                                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic' }}>None detected</span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Perplexity-style citation pills */}
                      {msg.sources?.length > 0 && !msg.streaming && (
                        <div style={styles.sourcePills}>
                          {msg.sources.map((src, si) => (
                            <button
                              key={si}
                              onClick={() => setSelectedSource(src)}
                              style={styles.sourcePill}
                              title={`${src.excerpt}\n\nClause: ${src.clause || 'N/A'}`}
                            >
                              <span style={styles.pillNum}>{src.index || si + 1}</span>
                              <FileText size={10} />
                              <span style={styles.pillName}>{src.document}</span>
                              {src.clause && src.clause !== 'Unknown' && (
                                <span style={{...styles.pillPage, color: 'var(--accent-red)'}}>§ {src.clause.split(' ')[1] || 'Sec'}</span>
                              )}
                              {src.page && <span style={styles.pillPage}>p.{src.page}</span>}
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {/* Workstream A: Render persistent file chips inside user bubble */}
                      {msg.fileChips && msg.fileChips.length > 0 && (
                        <div style={fileChipStyles.container}>
                          {msg.fileChips.map((chip, ci) => (
                            <div key={ci} style={fileChipStyles.chip}>
                              {chip.type === 'image' && chip.preview ? (
                                <img src={chip.preview} alt={chip.name} style={fileChipStyles.preview} />
                              ) : (
                                <FileText size={14} color="rgba(255,255,255,0.75)" />
                              )}
                              <span style={fileChipStyles.name}>{chip.name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {/* Legacy: fallback for messages without fileChips */}
                      {!msg.fileChips && msg.image && (
                        <img src={msg.image} alt="Uploaded attachment" style={{ maxWidth: '200px', borderRadius: '8px', border: '1px solid var(--border)' }} />
                      )}
                      {msg.content && <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.content}</p>}
                    </div>
                  )}
                  {/* Timestamp & Confidence */}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                    {msg.timestamp && (
                      <div style={styles.timestamp}>{formatTimestamp(msg.timestamp)}</div>
                    )}
                    {msg.confidence_score !== undefined && (
                      <div style={{...styles.timestamp, color: msg.confidence_score > 0.5 ? 'var(--accent-green)' : 'var(--accent-amber)'}} title="Retrieval Confidence Score">
                        {Math.round(msg.confidence_score * 100)}% Confidence
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* ── Input Bar ── */}
        <div style={styles.inputBarWrap}>

          {/* Active upload jobs strip */}
          {uploadJobs.length > 0 && (
            <div style={{ padding: '8px 12px', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', marginBottom: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {uploadJobs.map(job => (
                <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                  {job.stage === 'done' ? <CheckCircle size={14} color="#22c55e" /> : job.stage === 'error' ? <XCircle size={14} color="#ef4444" /> : <Loader2 size={14} style={{ animation: 'spin 1s linear infinite', color: 'var(--primary)' }} />}
                  <span style={{ color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.filename}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', textTransform: 'capitalize' }}>{job.stage.replace(/_/g, ' ')}</span>
                  {job.stage !== 'done' && job.stage !== 'error' && (
                    <div style={{ width: '60px', height: '4px', background: 'var(--border)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ width: `${job.progress}%`, height: '100%', background: 'var(--primary)', transition: 'width 0.3s' }} />
                    </div>
                  )}
                  {job.stage === 'done' && (
                    <span style={{ fontSize: '11px', color: '#22c55e' }}>Indexed</span>
                  )}
                  {job.stage === 'error' && (
                    <span style={{ fontSize: '11px', color: '#ef4444' }}>{job.error}</span>
                  )}
                  <button onClick={() => setUploadJobs(prev => prev.filter(j => j.id !== job.id))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '0' }}><X size={12} /></button>
                </div>
              ))}
            </div>
          )}

          {/* Upload wizard */}
          {showUploadWizard && uploadQueue.length > 0 && (
            <div style={{ padding: '12px', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>Upload Documents</span>
                <button onClick={() => { setShowUploadWizard(false); setUploadQueue([]); }} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={14} /></button>
              </div>
              {uploadQueue.map((item, idx) => (
                <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '10px', background: 'var(--bg-card)', borderRadius: 'var(--radius-sm)', marginBottom: '8px', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FolderOpen size={14} color="var(--primary)" />
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.file.name}</span>
                    <button onClick={() => removeFromQueue(idx)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={12} /></button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <select
                      value={item.document_type}
                      onChange={e => updateUploadField(idx, 'document_type', e.target.value)}
                      style={{ padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-page)', color: 'var(--text-secondary)', fontSize: '12px' }}
                    >
                      <option value="">Auto-detect type</option>
                      <option value="bid">Bid / Proposal</option>
                      <option value="standard">Standard / SOTR</option>
                      <option value="subject">Subject Document</option>
                    </select>
                    <input
                      type="text"
                      placeholder="Bidder / Company"
                      value={item.bidder_key}
                      onChange={e => updateUploadField(idx, 'bidder_key', e.target.value)}
                      style={{ padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-page)', color: 'var(--text-secondary)', fontSize: '12px' }}
                    />
                  </div>
                  <input
                    type="text"
                    placeholder="Tender / Problem reference"
                    value={item.problem_statement}
                    onChange={e => updateUploadField(idx, 'problem_statement', e.target.value)}
                    style={{ padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-page)', color: 'var(--text-secondary)', fontSize: '12px' }}
                  />
                </div>
              ))}
              <button
                onClick={startUploads}
                style={{ width: '100%', padding: '8px', background: 'var(--primary)', color: '#fff', border: 'none', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
              >
                <Upload size={14} />
                Upload {uploadQueue.length} document{uploadQueue.length > 1 ? 's' : ''}
              </button>
            </div>
          )}

          {selectedFiles.length > 0 && (
            <div style={{ padding: '8px 12px', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', marginBottom: '8px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
              {selectedFiles.map((file, idx) => (
                <div key={idx} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '6px', padding: '4px 10px' }}>
                  {file.type.startsWith('image/') && <img src={URL.createObjectURL(file)} alt="" style={{ height: '22px', borderRadius: '3px' }} />}
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{file.name}</span>
                  <button onClick={() => setSelectedFiles(prev => prev.filter((_, i) => i !== idx))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={12} /></button>
                </div>
              ))}
              <button onClick={() => setSelectedFiles([])} style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'transparent', border: 'none', cursor: 'pointer' }}>Clear all</button>
              {selectedFiles.length === 1 && (
                <button
                  onClick={handleDrawingExtract}
                  style={{ padding: '4px 8px', background: 'var(--primary)', color: '#fff', border: 'none', borderRadius: '4px', fontSize: '11px', cursor: 'pointer', marginLeft: 'auto', opacity: isPollingDrawing ? 0.6 : 1 }}
                  disabled={isPollingDrawing}
                >
                  {isPollingDrawing ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : 'Extract'}
                </button>
              )}
            </div>
          )}

          {attachedDocs.length > 0 && (
            <div style={{ padding: '8px 12px', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', marginBottom: '8px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
              {attachedDocs.map((file, idx) => (
                <div key={idx} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '6px', padding: '4px 10px' }}>
                  <FileText size={14} color="var(--primary)" />
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{file.name}</span>
                  <button onClick={() => setAttachedDocs(prev => prev.filter((_, i) => i !== idx))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={12} /></button>
                </div>
              ))}
              <button onClick={() => setAttachedDocs([])} style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'transparent', border: 'none', cursor: 'pointer' }}>Clear all</button>
            </div>
          )}
          <div style={styles.inputBar}>
            <button onClick={() => fileInputRef.current?.click()} style={styles.attachBtn} title="Attach file" id="attach-file-btn">
              <Paperclip size={17} />
            </button>
            <input type="file" multiple ref={fileInputRef} style={{ display: 'none' }} accept="image/*,.pdf,.docx,.doc,.txt" onChange={handleFileAttach} />
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isHindi ? "कोई प्रश्न पूछें, या टाइप करें 'एक पीपीटी बनाएं...'..." : "Ask a question, or type 'create a PPT about…', 'generate a quiz', 'summarize'…"}
              rows={1}
              style={styles.textarea}
              id="chat-input"
            />
            <button
              onClick={handleSend}
              disabled={(!input.trim() && attachedDocs.length === 0 && selectedFiles.length === 0) || isSessionStreaming || draft.isUploading}
              style={{ ...styles.sendBtn, opacity: ((!input.trim() && attachedDocs.length === 0 && selectedFiles.length === 0) || isSessionStreaming || draft.isUploading) ? 0.4 : 1 }}
              id="send-btn"
              title={draft.isUploading ? 'Uploading files…' : 'Send message'}
            >
              {draft.isUploading
                ? <Loader2 size={17} style={{ animation: 'spin 1s linear infinite', color: '#f59e0b' }} />
                : isSessionStreaming
                  ? <Loader2 size={17} style={{ animation: 'spin 1s linear infinite' }} />
                  : <Send size={17} />
              }
            </button>
          </div>
          <div style={styles.disclaimer}>
            AGRA processes all queries locally — zero telemetry, zero cloud.
          </div>
        </div>
      </main>

      {/* ── Source Side Panel ── */}
      {selectedSource && (
        <SourcePanel
          source={selectedSource}
          onClose={() => setSelectedSource(null)}
          apiUrl={apiUrl}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   STYLES
═══════════════════════════════════════════════════════ */

const styles = {
  layout: { display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg-page)' },

  /* Sidebar */
  sidebar: { display: 'flex', flexDirection: 'column', background: 'var(--sidebar-bg)', borderRight: '1px solid var(--sidebar-border)', transition: 'width 0.2s ease, min-width 0.2s ease', overflow: 'hidden' },
  sidebarHeader: { padding: '14px 12px 10px', borderBottom: '1px solid var(--sidebar-border-inner)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  logoGroup: { display: 'flex', alignItems: 'center', gap: '9px' },
  logoIcon: { width: 34, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '9px', background: 'rgba(74,139,255,0.12)', flexShrink: 0 },
  logoText: { fontSize: '15px', fontWeight: 800, color: 'var(--sidebar-text)', letterSpacing: '1.5px' },
  logoSub: { fontSize: '9px', color: 'var(--sidebar-text-muted)', fontWeight: 500, letterSpacing: '0.3px' },
  collapseBtn: { background: 'transparent', border: 'none', color: 'var(--sidebar-text)', padding: '4px', borderRadius: '6px', cursor: 'pointer', display: 'flex', opacity: 0.7 },
  newChatBtn: { display: 'flex', alignItems: 'center', gap: '8px', margin: '10px 10px 6px', padding: '9px 12px', background: 'var(--primary)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, border: 'none', justifyContent: 'center', cursor: 'pointer' },
  sessionList: { flex: 1, overflowY: 'auto', padding: '4px 6px' },
  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', padding: '28px 14px', color: 'var(--sidebar-text-muted)', fontSize: '12px' },
  sessionItem: { display: 'flex', alignItems: 'center', gap: '7px', padding: '8px 10px', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '12px', color: 'var(--sidebar-text-dim)', transition: 'background 0.15s', marginBottom: '1px' },
  sessionTitle: { flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  sessionDeleteBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, borderRadius: '50%', background: 'transparent', color: 'var(--sidebar-text-muted)', border: 'none', opacity: 0, transition: 'opacity 0.15s', cursor: 'pointer' },
  navSection: { padding: '6px 6px', borderTop: '1px solid var(--sidebar-border-inner)' },
  navLink: { display: 'flex', alignItems: 'center', gap: '9px', padding: '8px 12px', borderRadius: 'var(--radius-sm)', fontSize: '12px', color: 'var(--sidebar-text-dim)', textDecoration: 'none', transition: 'background 0.15s' },
  sidebarFooter: { padding: '10px', borderTop: '1px solid var(--sidebar-border-inner)' },
  userInfo: { display: 'flex', alignItems: 'center', gap: '7px', padding: '5px 4px', marginBottom: '5px' },
  userAvatar: { width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'rgba(74,139,255,0.15)', color: 'var(--sidebar-text)', flexShrink: 0 },
  userName: { fontSize: '11px', color: 'var(--sidebar-text-dim)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  logoutBtn: { display: 'flex', alignItems: 'center', gap: '7px', width: '100%', padding: '7px 10px', background: 'transparent', color: '#ff6b4a', borderRadius: 'var(--radius-sm)', fontSize: '12px', fontWeight: 500, border: 'none', cursor: 'pointer' },

  /* Main */
  main: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' },

  /* Welcome */
  welcome: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 24px', textAlign: 'center' },
  welcomeIcon: { width: 72, height: 72, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'rgba(74,139,255,0.08)', border: '1px solid rgba(74,139,255,0.2)', marginBottom: '18px' },
  welcomeTitle: { fontSize: '26px', fontWeight: 700, color: 'var(--text-heading)', marginBottom: '10px', background: 'linear-gradient(135deg, var(--text-heading), #1e6bff)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' },
  welcomeDesc: { fontSize: '14px', color: 'var(--text-secondary)', maxWidth: '480px', lineHeight: '1.7', marginBottom: '32px' },
  suggestionsGrid: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: '10px', maxWidth: '560px', width: '100%' },
  suggestionCard: { padding: '13px 15px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', color: 'var(--text-secondary)', fontSize: '13px', textAlign: 'left', cursor: 'pointer', lineHeight: '1.5', transition: 'border-color 0.15s, background 0.15s', display: 'flex', alignItems: 'flex-start', gap: '8px' },
  suggestionIcon: { flexShrink: 0, marginTop: '2px', opacity: 0.6 },

  /* Messages */
  messagesContainer: { flex: 1, overflowY: 'auto', padding: '20px 20px 10px' },
  msgRow: { display: 'flex', gap: '10px', marginBottom: '14px', alignItems: 'flex-start' },
  aiAvatar: { width: 30, height: 30, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'rgba(74,139,255,0.12)', flexShrink: 0, marginTop: '4px' },
  bubble: { maxWidth: '76%', borderRadius: 'var(--radius-lg)', padding: '11px 15px', fontSize: '14px', lineHeight: '1.65' },
  userBubble: { background: 'var(--user-bubble-bg)', color: 'var(--user-bubble-color)', borderBottomRightRadius: '4px' },
  aiBubble: { background: 'var(--ai-bubble-bg)', border: '1px solid var(--ai-bubble-border)', color: 'var(--text-primary)', borderBottomLeftRadius: '4px' },
  cursor: { display: 'inline-block', color: 'var(--primary)', animation: 'typingBlink 0.8s infinite', marginLeft: '2px', fontSize: '15px' },
  timestamp: { fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px', paddingLeft: '2px' },

  /* Perplexity Citation Pills */
  sourcePills: { display: 'flex', flexWrap: 'wrap', gap: '5px', marginTop: '10px', paddingTop: '8px', borderTop: '1px solid var(--border)' },
  sourcePill: { display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', background: 'rgba(74,139,255,0.06)', border: '1px solid rgba(74,139,255,0.2)', borderRadius: '20px', fontSize: '11px', color: 'var(--text-secondary)', cursor: 'pointer', transition: 'background 0.15s, border-color 0.15s', fontFamily: 'var(--font-sans)' },
  pillNum: { width: '16px', height: '16px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'var(--primary)', color: '#fff', fontSize: '9px', fontWeight: 700, flexShrink: 0 },
  pillName: { maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  pillPage: { color: 'var(--text-muted)', fontSize: '10px' },

  /* Input */
  inputBarWrap: { padding: '10px 20px 14px', borderTop: '1px solid var(--border)', background: 'var(--bg-page)' },
  inputBar: { display: 'flex', alignItems: 'flex-end', gap: '6px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '5px 7px', transition: 'border-color 0.15s' },
  attachBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36, borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--text-muted)', border: 'none', cursor: 'pointer', flexShrink: 0 },
  textarea: { flex: 1, background: 'transparent', border: 'none', color: 'var(--text-primary)', fontSize: '14px', resize: 'none', padding: '8px 4px', lineHeight: '1.5', outline: 'none', fontFamily: 'var(--font-sans)', maxHeight: '120px', minHeight: '36px' },
  sendBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36, borderRadius: 'var(--radius-md)', background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer', flexShrink: 0, transition: 'opacity 0.15s' },
  disclaimer: { fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center', marginTop: '6px' },
};

/* ── Quiz sub-styles ── */
const quizStyles = {
  container: { marginTop: '12px', borderTop: '1px solid var(--border)', paddingTop: '10px' },
  header: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' },
  headerText: { fontWeight: 700, fontSize: '14px', color: 'var(--text-primary)', flex: 1 },
  badge: { fontSize: '11px', color: 'var(--text-muted)', background: 'rgba(124,110,247,0.1)', padding: '2px 8px', borderRadius: '10px', border: '1px solid rgba(124,110,247,0.2)' },
  question: { marginBottom: '16px', padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' },
  questionText: { margin: '0 0 10px', fontSize: '13px', color: 'var(--text-primary)', lineHeight: '1.5' },
  options: { display: 'flex', flexDirection: 'column', gap: '6px' },
  option: { display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid', fontSize: '13px', textAlign: 'left', cursor: 'pointer', transition: 'all 0.15s', fontFamily: 'var(--font-sans)' },
  optKey: { width: '22px', height: '22px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'rgba(255,255,255,0.08)', fontWeight: 700, fontSize: '11px', flexShrink: 0 },
  explanation: { display: 'flex', alignItems: 'flex-start', marginTop: '8px', padding: '6px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px' },
  revealBtn: { marginTop: '8px', padding: '5px 12px', background: 'rgba(74,139,255,0.1)', border: '1px solid rgba(74,139,255,0.25)', borderRadius: '20px', color: 'var(--primary)', fontSize: '12px', cursor: 'pointer', fontFamily: 'var(--font-sans)' },
  details: { marginTop: '8px' },
  summary: { fontSize: '12px', color: 'var(--primary)', cursor: 'pointer', padding: '4px 0' },
  modelAnswer: { fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px', padding: '8px', background: 'rgba(52,211,153,0.06)', borderRadius: '6px', border: '1px solid rgba(52,211,153,0.15)' },
};

/* ── PPT card styles ── */
const pptStyles = {
  card: { display: 'flex', alignItems: 'center', gap: '12px', marginTop: '12px', padding: '12px 14px', background: 'rgba(74,139,255,0.06)', border: '1px solid rgba(74,139,255,0.2)', borderRadius: 'var(--radius-md)' },
  icon: { width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '10px', background: 'rgba(74,139,255,0.1)', flexShrink: 0 },
  info: { flex: 1, minWidth: 0 },
  title: { fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' },
  dlBtn: { display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '7px 14px', background: 'var(--primary)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '12px', fontWeight: 600, textDecoration: 'none', flexShrink: 0, transition: 'opacity 0.15s' },
};

/* ── Source side panel ── */
const panelStyles = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', justifyContent: 'flex-end' },
  panel: { width: '400px', maxWidth: '90vw', background: 'var(--bg-surface)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', padding: '0', animation: 'slideInRight 0.2s ease', overflow: 'hidden' },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', borderBottom: '1px solid var(--border)' },
  headerLeft: { display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 },
  filename: { fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  page: { padding: '2px 7px', background: 'rgba(74,139,255,0.15)', color: 'var(--primary)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, flexShrink: 0 },
  closeBtn: { background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px', borderRadius: '6px', display: 'flex', flexShrink: 0 },
  excerptSection: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  excerptLabel: { padding: '10px 16px 0', flexShrink: 0 },
  excerpt: { flex: 1, padding: '10px 16px 16px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.7', overflowY: 'auto', whiteSpace: 'pre-wrap' },
  downloadBtn: { display: 'flex', alignItems: 'center', gap: '7px', padding: '10px 16px', background: 'var(--primary)', color: '#fff', borderRadius: 'var(--radius-md)', fontSize: '13px', fontWeight: 600, textDecoration: 'none', justifyContent: 'center', transition: 'opacity 0.15s' },
};

/* ── Workstream A: File chip styles for user bubbles ── */
const fileChipStyles = {
  container: {
    display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '4px',
  },
  chip: {
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '4px 10px', borderRadius: '8px',
    background: 'rgba(255,255,255,0.12)',
    border: '1px solid rgba(255,255,255,0.18)',
    backdropFilter: 'blur(4px)',
    transition: 'background 0.15s',
  },
  preview: {
    height: '24px', width: '24px', objectFit: 'cover',
    borderRadius: '4px', flexShrink: 0,
  },
  name: {
    fontSize: '11px', fontWeight: 500,
    color: 'rgba(255,255,255,0.85)',
    maxWidth: '120px', overflow: 'hidden',
    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
};

// Global styles for animations
const styleSheet = document.createElement("style");
styleSheet.type = "text/css";
styleSheet.innerText = `
  @keyframes slideIn {
    from { transform: translateX(120%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
`;
document.head.appendChild(styleSheet);

