/**
 * AGRA Agent — Upload Page
 * Drag-drop document manager with ingestion progress and document table.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Upload as UploadIcon, FileText, Trash2, ArrowLeft, CheckCircle2,
  AlertCircle, Clock, Loader2, File, Image, X, RefreshCw, HardDrive,
  Search, Filter, ChevronUp, ChevronDown,
} from 'lucide-react';
import api, { getApiUrl } from '../utils/api';
import { getToken } from '../utils/auth';
import { formatDistanceToNow } from 'date-fns';

const ACCEPTED_TYPES = ['.pdf', '.docx', '.doc', '.txt', '.jpg', '.jpeg', '.png'];
const STATUS_MAP = {
  indexed:     { label: 'Indexed',     color: '#00c853', bg: 'rgba(0,200,83,0.12)',    icon: CheckCircle2 },
  processing:  { label: 'Processing',  color: '#f0b429', bg: 'rgba(240,180,41,0.12)',   icon: Clock },
  failed:      { label: 'Failed',      color: '#ff4757', bg: 'rgba(255,71,87,0.12)',    icon: AlertCircle },
};

export default function UploadPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [docSearch, setDocSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('filename');
  const [sortDir, setSortDir] = useState('asc');
  const fileInputRef = useRef(null);
  const versionInputRef = useRef(null);
  const [versionTarget, setVersionTarget] = useState(null);
  const token = getToken();

  // Sort handler
  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('asc'); }
  };

  // Filtered + sorted documents
  const filteredDocs = useMemo(() => {
    let list = documents.filter(d => {
      const q = docSearch.toLowerCase();
      if (q && !d.filename?.toLowerCase().includes(q)) return false;
      if (statusFilter !== 'all' && d.status !== statusFilter) return false;
      return true;
    });
    list.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      av = (av || '').toString().toLowerCase();
      bv = (bv || '').toString().toLowerCase();
      return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    return list;
  }, [documents, docSearch, statusFilter, sortKey, sortDir]);

  // ── Fetch documents ──
  const fetchDocuments = useCallback(async () => {
    try {
      const { data } = await api.get('/documents');
      setDocuments(data.documents || []);
    } catch (err) {
      console.error('Fetch documents error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, [fetchDocuments]);

  // ── Upload handler ──
  const uploadFile = async (file, parentDocId = null, versionNotes = null) => {
    const id = Date.now() + '_' + Math.random().toString(36).slice(2, 6);
    const queueItem = {
      id,
      name: file.name,
      size: file.size,
      progress: 0,
      status: 'uploading',
      message: 'Starting upload...',
    };

    setUploadQueue(prev => [...prev, queueItem]);

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (parentDocId) {
        formData.append('parent_doc_id', parentDocId);
      }
      if (versionNotes) {
        formData.append('version_notes', versionNotes);
      }

      const response = await fetch(getApiUrl('/api/agent/upload'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const err = await response.text();
        throw new Error(err);
      }

      // Read SSE stream for progress
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(trimmed.slice(6));
            setUploadQueue(prev =>
              prev.map(q =>
                q.id === id
                  ? {
                      ...q,
                      progress: data.progress || q.progress,
                      status: data.status || q.status,
                      message: data.message || q.message,
                    }
                  : q
              )
            );
          } catch {}
        }
      }

      // Mark complete
      setUploadQueue(prev =>
        prev.map(q =>
          q.id === id
            ? { ...q, progress: 100, status: 'done', message: 'Indexed successfully' }
            : q
        )
      );

      // Refresh document list
      setTimeout(fetchDocuments, 1000);
    } catch (err) {
      setUploadQueue(prev =>
        prev.map(q =>
          q.id === id
            ? { ...q, status: 'error', message: err.message }
            : q
        )
      );
    }
  };

  const handleFiles = (files) => {
    Array.from(files).forEach(file => {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (ACCEPTED_TYPES.includes(ext)) {
        uploadFile(file);
      }
    });
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleVersionClick = (docId) => {
    setVersionTarget(docId);
    versionInputRef.current?.click();
  };

  const handleVersionFiles = (files) => {
    if (!versionTarget) return;
    const versionNotes = window.prompt("Enter version notes (optional):", "Minor revision");
    Array.from(files).forEach(file => {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (ACCEPTED_TYPES.includes(ext)) {
        uploadFile(file, versionTarget, versionNotes);
      }
    });
    setVersionTarget(null);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDelete = async (docId) => {
    if (!window.confirm('Delete this document and all its indexed data?')) return;
    try {
      await api.delete(`/documents/${docId}`);
      setDocuments(prev => prev.filter(d => d.doc_id !== docId));
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  const removeQueueItem = (id) => {
    setUploadQueue(prev => prev.filter(q => q.id !== id));
  };

  const formatBytes = (bytes) => {
    if (!bytes) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  };

  const getFileIcon = (filename) => {
    const ext = filename?.split('.').pop()?.toLowerCase();
    if (['jpg', 'jpeg', 'png'].includes(ext)) return <Image size={16} color="#f0b429" />;
    return <FileText size={16} color="#4a8bff" />;
  };

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <Link to="/" style={styles.backLink}>
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 style={styles.title}>Document Manager</h1>
          <p style={styles.subtitle}>Upload, index, and manage your knowledge base documents</p>
        </div>
        <button onClick={fetchDocuments} style={styles.refreshBtn} title="Refresh">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        style={{
          ...styles.dropZone,
          borderColor: isDragging ? 'var(--primary)' : 'var(--border)',
          background: isDragging ? 'rgba(74, 139, 255, 0.06)' : 'var(--bg-card)',
        }}
        id="drop-zone"
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES.join(',')}
          onChange={(e) => handleFiles(e.target.files)}
          style={{ display: 'none' }}
        />
        <input
          ref={versionInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          onChange={(e) => handleVersionFiles(e.target.files)}
          style={{ display: 'none' }}
        />
        <div style={styles.dropIcon}>
          <UploadIcon size={28} color={isDragging ? '#4a8bff' : '#556688'} />
        </div>
        <div style={styles.dropTitle}>
          {isDragging ? 'Drop files here' : 'Drag & drop files to upload'}
        </div>
        <div style={styles.dropDesc}>
          or click to browse  •  PDF, DOCX, TXT, JPG, PNG  •  Max 50 MB
        </div>
      </div>

      {/* Upload Queue */}
      {uploadQueue.length > 0 && (
        <div style={styles.queueSection}>
          <h3 style={styles.sectionTitle}>Upload Queue</h3>
          <div style={styles.queueList}>
            {uploadQueue.map(item => (
              <div key={item.id} style={styles.queueItem} className="animate-slide-up">
                <div style={styles.queueLeft}>
                  <File size={16} color="var(--primary)" />
                  <div>
                    <div style={styles.queueName}>{item.name}</div>
                    <div style={styles.queueMsg}>{item.message}</div>
                  </div>
                </div>
                <div style={styles.queueRight}>
                  {item.status === 'uploading' || item.status === 'processing' ? (
                    <div style={styles.progressBarOuter}>
                      <div
                        style={{
                          ...styles.progressBarInner,
                          width: `${Math.max(item.progress, 5)}%`,
                        }}
                      />
                    </div>
                  ) : item.status === 'done' ? (
                    <CheckCircle2 size={18} color="#00c853" />
                  ) : (
                    <AlertCircle size={18} color="#ff4757" />
                  )}
                  <button onClick={() => removeQueueItem(item.id)} style={styles.queueClose}>
                    <X size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Documents Table */}
      <div style={styles.tableSection}>
        <div style={styles.tableHeader}>
          <h3 style={styles.sectionTitle}>
            <HardDrive size={18} />
            Indexed Documents
          </h3>
          <span style={styles.docCount}>{filteredDocs.length} of {documents.length} document{documents.length !== 1 ? 's' : ''}</span>
        </div>

        {/* Search + Filter Toolbar */}
        <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '200px', padding: '8px 12px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <Search size={14} color="var(--text-muted)" />
            <input value={docSearch} onChange={e => setDocSearch(e.target.value)} placeholder="Search documents…" style={{ flex: 1, border: 'none', background: 'transparent', color: 'var(--text-primary)', fontSize: '13px', outline: 'none' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 12px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <Filter size={13} color="var(--text-muted)" />
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ border: 'none', background: 'transparent', color: 'var(--text-primary)', fontSize: '13px', outline: 'none', cursor: 'pointer' }}>
              <option value="all">All Status</option>
              <option value="indexed">Indexed</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>

        <div style={styles.tableContainer}>
          {loading ? (
            <div style={styles.loadingBox}>
              <Loader2 size={28} style={{ animation: 'spin 1s linear infinite' }} color="var(--primary)" />
              <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading documents...</span>
            </div>
          ) : filteredDocs.length === 0 ? (
            <div style={styles.emptyBox}>
              <FileText size={32} style={{ opacity: 0.2 }} />
              <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{documents.length === 0 ? 'No documents uploaded yet' : 'No documents match your filters'}</span>
            </div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr style={styles.tableHeadRow}>
                  {[
                    { key: 'filename', label: 'File' },
                    { key: 'type', label: 'Type' },
                    { key: 'chunks', label: 'Chunks' },
                    { key: 'page_count', label: 'Pages' },
                    { key: 'status', label: 'Status' },
                    { key: '_del', label: '' },
                  ].map(col => (
                    <th
                      key={col.key}
                      onClick={col.key !== '_del' ? () => handleSort(col.key) : undefined}
                      style={{ ...styles.th, cursor: col.key !== '_del' ? 'pointer' : 'default', userSelect: 'none' }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                        {col.label}
                        {col.key !== '_del' && (
                          sortKey === col.key
                            ? (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)
                            : <ChevronUp size={11} style={{ opacity: 0.2 }} />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map((doc) => {
                  const ext = doc.filename?.split('.').pop()?.toUpperCase() || '—';
                  const statusInfo = STATUS_MAP[doc.status] || STATUS_MAP.indexed;
                  const StatusIcon = statusInfo.icon;
                  return (
                    <tr key={doc.doc_id} style={styles.tr}>
                      <td style={styles.td}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {getFileIcon(doc.filename)}
                          <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                            {doc.filename}
                          </span>
                        </div>
                      </td>
                      <td style={styles.td}>
                        <span style={styles.typeBadge}>{ext}</span>
                      </td>
                      <td style={{ ...styles.td, fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                        {doc.chunks || 0}
                      </td>
                      <td style={{ ...styles.td, fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                        {doc.page_count || 0}
                      </td>
                      <td style={styles.td}>
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '3px 10px',
                          borderRadius: '12px',
                          fontSize: '11px',
                          fontWeight: 600,
                          background: statusInfo.bg,
                          color: statusInfo.color,
                        }}>
                          <StatusIcon size={12} />
                          {statusInfo.label}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            onClick={() => handleVersionClick(doc.doc_id)}
                            style={styles.actionBtn}
                            title="Upload new version"
                          >
                            <UploadIcon size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(doc.doc_id)}
                            style={styles.actionBtn}
                            title="Delete document"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    padding: '28px 32px',
    maxWidth: '1200px',
    margin: '0 auto',
    minHeight: '100vh',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    marginBottom: '28px',
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
  refreshBtn: {
    marginLeft: 'auto',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 36,
    height: 36,
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    color: 'var(--text-secondary)',
  },

  /* Drop Zone */
  dropZone: {
    border: '2px dashed var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '48px 24px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'border-color 0.2s, background 0.2s',
    marginBottom: '28px',
  },
  dropIcon: {
    width: 56,
    height: 56,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '50%',
    background: 'rgba(85, 102, 136, 0.1)',
    margin: '0 auto 12px',
  },
  dropTitle: {
    fontSize: '16px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '6px',
  },
  dropDesc: {
    fontSize: '13px',
    color: 'var(--text-muted)',
  },

  /* Queue */
  queueSection: {
    marginBottom: '28px',
  },
  sectionTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '15px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '12px',
  },
  queueList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  queueItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
  },
  queueLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  queueName: {
    fontSize: '13px',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  queueMsg: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
  queueRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  progressBarOuter: {
    width: 120,
    height: 6,
    background: 'var(--border)',
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBarInner: {
    height: '100%',
    background: 'linear-gradient(90deg, #4a8bff, #5e9aff)',
    borderRadius: 3,
    transition: 'width 0.3s ease',
    backgroundSize: '40px 6px',
    animation: 'progressStripe 0.6s linear infinite',
  },
  queueClose: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    borderRadius: '50%',
    background: 'transparent',
    color: 'var(--text-muted)',
    border: 'none',
  },

  /* Table */
  tableSection: {},
  tableHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '12px',
  },
  docCount: {
    fontSize: '12px',
    color: 'var(--text-muted)',
  },
  tableContainer: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    overflow: 'hidden',
    boxShadow: 'var(--shadow-md)',
  },
  loadingBox: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '12px',
    padding: '60px',
  },
  emptyBox: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '12px',
    padding: '60px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  tableHeadRow: {
    background: 'var(--bg-surface)',
  },
  th: {
    textAlign: 'left',
    padding: '12px 16px',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    borderBottom: '1px solid var(--border)',
  },
  tr: {
    borderBottom: '1px solid var(--border)',
    transition: 'background 0.1s',
  },
  td: {
    padding: '12px 16px',
    fontSize: '13px',
    color: 'var(--text-secondary)',
  },
  typeBadge: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: '10px',
    fontWeight: 700,
    background: 'rgba(74, 139, 255, 0.1)',
    color: 'var(--primary)',
    letterSpacing: '0.5px',
  },
  actionBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 30,
    height: 30,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-input)',
    color: 'var(--text-muted)',
    border: '1px solid var(--border)',
    transition: 'color 0.15s, background 0.15s',
    cursor: 'pointer',
  },
};
