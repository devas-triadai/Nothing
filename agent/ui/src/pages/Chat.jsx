/**
 * AGRA Agent — Chat Page
 * Main conversational Q&A interface with SSE streaming.
 * Perplexity-inspired dark UI with RAG citations.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  MessageSquare, Plus, Send, Paperclip, ChevronDown, ChevronRight,
  Upload, FileText, ShieldCheck, LogOut, User, Loader2, X, Bot, Sparkles,
} from 'lucide-react';
import { getToken, getUser, decodeToken, logout } from '../utils/auth';
import { getApiUrl } from '../utils/api';
import { connectStream } from '../utils/stream';
import { renderMarkdown } from '../utils/markdown';

const SESSIONS_KEY = 'agra_chat_sessions';
const ACTIVE_KEY = 'agra_active_session';

function loadSessions() {
  try {
    return JSON.parse(localStorage.getItem(SESSIONS_KEY) || '[]');
  } catch { return []; }
}

function saveSessions(sessions) {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
}

function newSessionId() {
  return 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
}

export default function Chat() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState(loadSessions);
  const [activeSessionId, setActiveSessionId] = useState(
    () => localStorage.getItem(ACTIVE_KEY) || null
  );
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [expandedSources, setExpandedSources] = useState({});
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const streamRef = useRef(null);

  const token = getToken();
  const user = token ? (getUser() || decodeToken(token)) : null;

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load messages for active session
  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem(ACTIVE_KEY, activeSessionId);
      const sess = sessions.find(s => s.id === activeSessionId);
      setMessages(sess?.messages || []);
    } else {
      setMessages([]);
    }
  }, [activeSessionId]);

  // Save messages to session
  const persistMessages = useCallback((msgs) => {
    if (!activeSessionId) return;
    setSessions(prev => {
      const updated = prev.map(s =>
        s.id === activeSessionId ? { ...s, messages: msgs, updatedAt: Date.now() } : s
      );
      saveSessions(updated);
      return updated;
    });
  }, [activeSessionId]);

  const createNewChat = () => {
    const id = newSessionId();
    const sess = {
      id,
      title: 'New Chat',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setSessions(prev => {
      const updated = [sess, ...prev];
      saveSessions(updated);
      return updated;
    });
    setActiveSessionId(id);
    setMessages([]);
    setInput('');
    inputRef.current?.focus();
  };

  const deleteSession = (id, e) => {
    e.stopPropagation();
    setSessions(prev => {
      const updated = prev.filter(s => s.id !== id);
      saveSessions(updated);
      return updated;
    });
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setMessages([]);
    }
  };

  const handleSend = async () => {
    const question = input.trim();
    if (!question || isStreaming) return;

    const userMsg = { role: 'user', content: question, timestamp: Date.now() };
    const aiMsg = { role: 'assistant', content: '', sources: [], timestamp: Date.now(), streaming: true };
    const updatedMsgs = [...messages, userMsg, aiMsg];

    setMessages(updatedMsgs);
    setInput('');
    setIsStreaming(true);

    // Create session if none active
    let sessId = activeSessionId;
    if (!sessId) {
      const id = newSessionId();
      const sess = {
        id,
        title: question.slice(0, 50),
        messages: updatedMsgs,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      setSessions(prev => {
        const updated = [sess, ...prev];
        saveSessions(updated);
        return updated;
      });
      setActiveSessionId(id);
      sessId = id;
    } else {
      // Update title and messages
      setSessions(prev => {
        const updated = prev.map(s =>
          s.id === sessId
            ? { ...s, title: s.title === 'New Chat' ? question.slice(0, 50) : s.title, messages: updatedMsgs, updatedAt: Date.now() }
            : s
        );
        saveSessions(updated);
        return updated;
      });
    }

    const history = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }));

    let accumulatedText = '';

    streamRef.current = connectStream(
      getApiUrl('/api/agent/chat'),
      { question, history, session_id: sessId },
      // onToken
      (data) => {
        if (data.token) {
          accumulatedText += data.token;
          setMessages(prev => {
            if (!prev || prev.length === 0) return prev;
            const copy = [...prev];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, content: accumulatedText };
            return copy;
          });
        }
      },
      // onDone
      (data) => {
        setIsStreaming(false);
        setMessages(prev => {
          if (!prev || prev.length === 0) return prev;
          const copy = [...prev];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = {
            ...last,
            content: accumulatedText || last?.content || '',
            sources: data?.sources || [],
            streaming: false,
          };
          // Persist to session
          const finalMsgs = copy;
          setSessions(sp => {
            const updated = sp.map(s =>
              s.id === sessId ? { ...s, messages: finalMsgs, updatedAt: Date.now() } : s
            );
            saveSessions(updated);
            return updated;
          });
          return copy;
        });
      },
      // onError
      (err) => {
        setIsStreaming(false);
        setMessages(prev => {
          if (!prev || prev.length === 0) return prev;
          const copy = [...prev];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = {
            ...last,
            content: accumulatedText || `Error: ${err.message}`,
            streaming: false,
            isError: true,
          };
          return copy;
        });
      }
    );
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleSources = (idx) => {
    setExpandedSources(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  // ── File quick-upload ──
  const fileInputRef = useRef(null);
  const handleFileAttach = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch(getApiUrl('/api/agent/upload'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (resp.ok) {
        setInput(prev => prev + ` [Uploaded: ${file.name}]`);
      }
    } catch (err) {
      console.error('Upload failed:', err);
    }
    e.target.value = '';
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      streamRef.current?.abort?.();
    };
  }, []);

  return (
    <div style={styles.layout}>
      {/* ── Sidebar ── */}
      <aside style={{
        ...styles.sidebar,
        width: sidebarCollapsed ? '60px' : '280px',
        minWidth: sidebarCollapsed ? '60px' : '280px',
      }}>
        {/* Logo */}
        <div style={styles.sidebarHeader}>
          <div style={styles.logoGroup}>
            <div style={styles.logoIcon}>
              <ShieldCheck size={20} color="#4a8bff" />
            </div>
            {!sidebarCollapsed && (
              <div>
                <div style={styles.logoText}>AGRA</div>
                <div style={styles.logoSub}>Secure Intelligence</div>
              </div>
            )}
          </div>
        </div>

        {/* New Chat */}
        <button
          onClick={createNewChat}
          style={styles.newChatBtn}
          id="new-chat-btn"
        >
          <Plus size={16} />
          {!sidebarCollapsed && <span>New Chat</span>}
        </button>

        {/* Session List */}
        {!sidebarCollapsed && (
          <div style={styles.sessionList}>
            {sessions.length === 0 && (
              <div style={styles.emptyState}>
                <MessageSquare size={18} style={{ opacity: 0.3 }} />
                <span>No conversations yet</span>
              </div>
            )}
            {sessions.map(sess => (
              <div
                key={sess.id}
                onClick={() => setActiveSessionId(sess.id)}
                style={{
                  ...styles.sessionItem,
                  background: activeSessionId === sess.id ? 'var(--primary-dim)' : 'transparent',
                  borderLeft: activeSessionId === sess.id ? '2px solid var(--primary)' : '2px solid transparent',
                }}
              >
                <MessageSquare size={14} style={{ flexShrink: 0, opacity: 0.5 }} />
                <span style={styles.sessionTitle}>{sess.title}</span>
                <button
                  onClick={(e) => deleteSession(sess.id, e)}
                  style={styles.sessionDeleteBtn}
                  title="Delete"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Nav Links */}
        <div style={styles.navSection}>
          <Link to="/upload" style={styles.navLink}>
            <Upload size={16} />
            {!sidebarCollapsed && <span>Documents</span>}
          </Link>
          <Link to="/generate" style={styles.navLink}>
            <FileText size={16} />
            {!sidebarCollapsed && <span>Generate</span>}
          </Link>
          <Link to="/compliance" style={styles.navLink}>
            <ShieldCheck size={16} />
            {!sidebarCollapsed && <span>Compliance</span>}
          </Link>
        </div>

        {/* User / Logout */}
        <div style={styles.sidebarFooter}>
          {!sidebarCollapsed && user && (
            <div style={styles.userInfo}>
              <div style={styles.userAvatar}>
                <User size={14} />
              </div>
              <span style={styles.userName}>{user.sub || user.username || 'Agent'}</span>
            </div>
          )}
          <button onClick={logout} style={styles.logoutBtn} title="Logout" id="logout-btn">
            <LogOut size={16} />
            {!sidebarCollapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* ── Main Chat Area ── */}
      <main style={styles.main}>
        {messages.length === 0 ? (
          /* Welcome Screen */
          <div style={styles.welcome}>
            <div style={styles.welcomeIcon}>
              <Sparkles size={40} color="#4a8bff" />
            </div>
            <h1 style={styles.welcomeTitle}>AGRA Intelligence Agent</h1>
            <p style={styles.welcomeDesc}>
              Air-gapped, secure document intelligence. Ask questions about your uploaded documents,
              generate reports, and run compliance checks — all processed locally.
            </p>
            <div style={styles.suggestionsGrid}>
              {[
                'Summarize the key findings from the latest inspection report',
                'What are the compliance requirements for vessel safety?',
                'Generate a training quiz from the operations manual',
                'Compare this bid against the procurement standards',
              ].map((q, i) => (
                <button
                  key={i}
                  onClick={() => { setInput(q); inputRef.current?.focus(); }}
                  style={styles.suggestionCard}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Messages */
          <div style={styles.messagesContainer}>
            {messages.map((msg, idx) => (
              <div
                key={idx}
                style={{
                  ...styles.messageBubbleRow,
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
                className="animate-fade-in"
              >
                {msg.role === 'assistant' && (
                  <div style={styles.aiAvatar}>
                    <Bot size={16} color="#4a8bff" />
                  </div>
                )}
                <div style={{
                  ...styles.messageBubble,
                  ...(msg.role === 'user' ? styles.userBubble : styles.aiBubble),
                  ...(msg.isError ? { borderColor: 'var(--accent-red)' } : {}),
                }}>
                  {msg.role === 'assistant' ? (
                    <>
                      <div
                        className="md-content"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                      />
                      {msg.streaming && (
                        <span style={styles.typingCursor}>▊</span>
                      )}
                      {/* Sources */}
                      {msg.sources?.length > 0 && !msg.streaming && (
                        <div style={styles.sourcesSection}>
                          <button
                            onClick={() => toggleSources(idx)}
                            style={styles.sourcesToggle}
                          >
                            {expandedSources[idx] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            <span>{msg.sources.length} Source{msg.sources.length !== 1 ? 's' : ''}</span>
                          </button>
                          {expandedSources[idx] && (
                            <div style={styles.sourcesGrid}>
                              {msg.sources.map((src, si) => (
                                <div key={si} style={styles.sourceCard}>
                                  <div style={styles.sourceFileName}>
                                    <FileText size={12} />
                                    {src.filename || src.doc_name || 'Document'}
                                  </div>
                                  {src.page && (
                                    <div style={styles.sourcePageBadge}>Page {src.page}</div>
                                  )}
                                  {(src.snippet || src.text) && (
                                    <div style={styles.sourceExcerpt}>
                                      {(src.snippet || src.text || '').slice(0, 200)}...
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.content}</p>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* ── Input Bar ── */}
        <div style={styles.inputBarContainer}>
          <div style={styles.inputBar}>
            <button
              onClick={() => fileInputRef.current?.click()}
              style={styles.attachBtn}
              title="Attach file"
              id="attach-file-btn"
            >
              <Paperclip size={18} />
            </button>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png"
              onChange={handleFileAttach}
            />
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your documents..."
              rows={1}
              style={styles.inputTextarea}
              id="chat-input"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              style={{
                ...styles.sendBtn,
                opacity: (!input.trim() || isStreaming) ? 0.4 : 1,
              }}
              id="send-btn"
            >
              {isStreaming ? (
                <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>
          <div style={styles.inputDisclaimer}>
            AGRA processes all queries locally. No data leaves this system.
          </div>
        </div>
      </main>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   STYLES
   ═══════════════════════════════════════════════════════════════ */
const styles = {
  layout: {
    display: 'flex',
    height: '100vh',
    overflow: 'hidden',
  },

  /* ── Sidebar ── */
  sidebar: {
    display: 'flex',
    flexDirection: 'column',
    background: '#0a0e1a',
    borderRight: '1px solid var(--border)',
    transition: 'width 0.2s ease, min-width 0.2s ease',
    overflow: 'hidden',
  },
  sidebarHeader: {
    padding: '18px 16px 12px',
    borderBottom: '1px solid var(--border)',
  },
  logoGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  logoIcon: {
    width: 36,
    height: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '10px',
    background: 'rgba(74, 139, 255, 0.12)',
    flexShrink: 0,
  },
  logoText: {
    fontSize: '16px',
    fontWeight: 800,
    color: '#fff',
    letterSpacing: '1.5px',
  },
  logoSub: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontWeight: 500,
    letterSpacing: '0.5px',
  },
  newChatBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    margin: '12px 12px 8px',
    padding: '10px 14px',
    background: 'var(--primary)',
    color: '#fff',
    borderRadius: 'var(--radius-md)',
    fontSize: '13px',
    fontWeight: 600,
    border: 'none',
    justifyContent: 'center',
  },
  sessionList: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 8px',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '8px',
    padding: '30px 16px',
    color: 'var(--text-muted)',
    fontSize: '12px',
  },
  sessionItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '9px 12px',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer',
    fontSize: '13px',
    color: 'var(--text-secondary)',
    transition: 'background 0.15s, border-left 0.15s',
    marginBottom: '2px',
  },
  sessionTitle: {
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  sessionDeleteBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 20,
    height: 20,
    borderRadius: '50%',
    background: 'transparent',
    color: 'var(--text-muted)',
    opacity: 0,
    transition: 'opacity 0.15s',
    border: 'none',
  },
  navSection: {
    padding: '8px 8px',
    borderTop: '1px solid var(--border)',
  },
  navLink: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '9px 14px',
    borderRadius: 'var(--radius-sm)',
    fontSize: '13px',
    color: 'var(--text-secondary)',
    textDecoration: 'none',
    transition: 'background 0.15s, color 0.15s',
  },
  sidebarFooter: {
    padding: '12px',
    borderTop: '1px solid var(--border)',
  },
  userInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 4px',
    marginBottom: '6px',
  },
  userAvatar: {
    width: 28,
    height: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    background: 'rgba(74, 139, 255, 0.15)',
    color: 'var(--primary)',
    flexShrink: 0,
  },
  userName: {
    fontSize: '12px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  logoutBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    width: '100%',
    padding: '8px 12px',
    background: 'transparent',
    color: 'var(--accent-red)',
    borderRadius: 'var(--radius-sm)',
    fontSize: '12px',
    fontWeight: 500,
    border: 'none',
    transition: 'background 0.15s',
  },

  /* ── Main ── */
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    position: 'relative',
  },

  /* ── Welcome ── */
  welcome: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px 24px',
    textAlign: 'center',
    animation: 'fadeIn 0.5s ease-out',
  },
  welcomeIcon: {
    width: 80,
    height: 80,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    background: 'rgba(74, 139, 255, 0.08)',
    border: '1px solid rgba(74, 139, 255, 0.2)',
    marginBottom: '20px',
  },
  welcomeTitle: {
    fontSize: '28px',
    fontWeight: 700,
    color: '#fff',
    marginBottom: '10px',
    background: 'linear-gradient(135deg, #fff, #4a8bff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  welcomeDesc: {
    fontSize: '14px',
    color: 'var(--text-secondary)',
    maxWidth: '520px',
    lineHeight: '1.7',
    marginBottom: '36px',
  },
  suggestionsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '10px',
    maxWidth: '580px',
    width: '100%',
  },
  suggestionCard: {
    padding: '14px 16px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-secondary)',
    fontSize: '13px',
    textAlign: 'left',
    cursor: 'pointer',
    lineHeight: '1.5',
    transition: 'border-color 0.15s, background 0.15s, color 0.15s',
  },

  /* ── Messages ── */
  messagesContainer: {
    flex: 1,
    overflowY: 'auto',
    padding: '24px 24px 16px',
  },
  messageBubbleRow: {
    display: 'flex',
    gap: '10px',
    marginBottom: '16px',
    alignItems: 'flex-start',
  },
  aiAvatar: {
    width: 32,
    height: 32,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    background: 'rgba(74, 139, 255, 0.12)',
    flexShrink: 0,
    marginTop: '4px',
  },
  messageBubble: {
    maxWidth: '72%',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 16px',
    fontSize: '14px',
    lineHeight: '1.6',
  },
  userBubble: {
    background: '#1a3a7a',
    color: '#e4ecff',
    borderBottomRightRadius: '4px',
  },
  aiBubble: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    borderBottomLeftRadius: '4px',
  },
  typingCursor: {
    display: 'inline-block',
    color: 'var(--primary)',
    animation: 'typingBlink 0.8s infinite',
    marginLeft: '2px',
    fontSize: '16px',
  },

  /* ── Sources ── */
  sourcesSection: {
    marginTop: '12px',
    borderTop: '1px solid var(--border)',
    paddingTop: '8px',
  },
  sourcesToggle: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    background: 'transparent',
    color: 'var(--primary)',
    fontSize: '12px',
    fontWeight: 600,
    padding: '4px 0',
    border: 'none',
  },
  sourcesGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: '8px',
    marginTop: '8px',
  },
  sourceCard: {
    background: 'rgba(74, 139, 255, 0.06)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    padding: '10px',
    fontSize: '11px',
  },
  sourceFileName: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '4px',
  },
  sourcePageBadge: {
    display: 'inline-block',
    background: 'rgba(74, 139, 255, 0.15)',
    color: 'var(--primary)',
    padding: '1px 6px',
    borderRadius: '4px',
    fontSize: '10px',
    fontWeight: 600,
    marginBottom: '4px',
  },
  sourceExcerpt: {
    color: 'var(--text-muted)',
    fontSize: '11px',
    lineHeight: '1.5',
  },

  /* ── Input Bar ── */
  inputBarContainer: {
    padding: '12px 24px 16px',
    borderTop: '1px solid var(--border)',
    background: 'var(--bg-page)',
  },
  inputBar: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '8px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '6px 8px',
    transition: 'border-color 0.15s',
  },
  attachBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 38,
    height: 38,
    borderRadius: 'var(--radius-md)',
    background: 'transparent',
    color: 'var(--text-muted)',
    border: 'none',
    flexShrink: 0,
  },
  inputTextarea: {
    flex: 1,
    background: 'transparent',
    border: 'none',
    color: 'var(--text-primary)',
    fontSize: '14px',
    resize: 'none',
    padding: '9px 4px',
    lineHeight: '1.5',
    outline: 'none',
    fontFamily: 'var(--font-sans)',
    maxHeight: '120px',
    minHeight: '38px',
  },
  sendBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 38,
    height: 38,
    borderRadius: 'var(--radius-md)',
    background: 'var(--primary)',
    color: '#fff',
    border: 'none',
    flexShrink: 0,
    transition: 'opacity 0.15s, transform 0.1s',
  },
  inputDisclaimer: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    textAlign: 'center',
    marginTop: '8px',
  },
};
