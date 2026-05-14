import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../utils/api'
import { getToken } from '../utils/auth'
import {
  FileText, Upload, Download, Trash2, Search, Filter, X, GitBranch,
  CheckCircle, AlertTriangle, Clock, Database, Cpu, Shield, Tag,
  ChevronDown, RefreshCw, Layers, Zap, Eye
} from 'lucide-react'

// ── Category color map ──
const CAT_COLORS = {
  'SOP': { bg: 'rgba(16,185,129,0.12)', color: '#10b981', border: 'rgba(16,185,129,0.3)' },
  'Standard': { bg: 'rgba(59,130,246,0.12)', color: '#3b82f6', border: 'rgba(59,130,246,0.3)' },
  'SOTR': { bg: 'rgba(139,92,246,0.12)', color: '#8b5cf6', border: 'rgba(139,92,246,0.3)' },
  'Blueprint': { bg: 'rgba(236,72,153,0.12)', color: '#ec4899', border: 'rgba(236,72,153,0.3)' },
  'Report': { bg: 'rgba(245,158,11,0.12)', color: '#f59e0b', border: 'rgba(245,158,11,0.3)' },
  'Compliance': { bg: 'rgba(239,68,68,0.12)', color: '#ef4444', border: 'rgba(239,68,68,0.3)' },
  'Bid Document': { bg: 'rgba(6,182,212,0.12)', color: '#06b6d4', border: 'rgba(6,182,212,0.3)' },
  'IMO Standard': { bg: 'rgba(99,102,241,0.12)', color: '#6366f1', border: 'rgba(99,102,241,0.3)' },
  'ICG Document': { bg: 'rgba(14,165,233,0.12)', color: '#0ea5e9', border: 'rgba(14,165,233,0.3)' },
  'Vessel Document': { bg: 'rgba(20,184,166,0.12)', color: '#14b8a6', border: 'rgba(20,184,166,0.3)' },
  'General': { bg: 'rgba(107,114,128,0.12)', color: '#6b7280', border: 'rgba(107,114,128,0.3)' },
}

const SOURCE_LABELS = {
  'knowledge_base': { label: 'Knowledge Base', icon: Database, color: '#8b5cf6' },
  'admin_upload': { label: 'Admin Upload', icon: Shield, color: '#3b82f6' },
  'agent_upload': { label: 'Agent Upload', icon: Cpu, color: '#10b981' },
}

function CategoryBadge({ category }) {
  const c = CAT_COLORS[category] || CAT_COLORS['General']
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    }}>
      <Tag size={10} />{category || 'General'}
    </span>
  )
}

function SourceBadge({ source }) {
  const s = SOURCE_LABELS[source] || SOURCE_LABELS['admin_upload']
  const Icon = s.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 5, fontSize: 10, fontWeight: 600,
      background: `${s.color}15`, color: s.color,
    }}>
      <Icon size={10} />{s.label}
    </span>
  )
}

function ConfidenceDot({ confidence }) {
  const pct = Math.round((confidence || 0) * 100)
  const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block' }} />
      {pct}%
    </span>
  )
}

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const [versionHistory, setVersionHistory] = useState(null)
  const [showHistoryModal, setShowHistoryModal] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState(null)
  const fileInputRef = useRef(null)

  useEffect(() => { fetchDocs() }, [])

  async function fetchDocs() {
    setLoading(true)
    try {
      const data = await apiFetch('/documents/')
      const items = Array.isArray(data) ? data : (data?.documents || [])
      setDocs(items)
    } catch (e) {
      console.error('Fetch docs error:', e)
    } finally {
      setLoading(false)
    }
  }

  // ── Smart Upload (drag-and-drop + file select, NO manual category) ──
  const handleFiles = useCallback(async (files) => {
    if (!files || files.length === 0) return
    setUploading(true)
    const progress = Array.from(files).map(f => ({
      name: f.name, status: 'uploading', category: null, message: 'Uploading...'
    }))
    setUploadProgress([...progress])

    const token = getToken()
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      try {
        const formData = new FormData()
        formData.append('file', file)
        // NO category field — server auto-classifies

        const res = await fetch('/api/documents/upload', {
          method: 'POST',
          headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: formData
        })
        const result = await res.json()
        if (res.ok) {
          const doc = result.document || result.duplicate_of
          progress[i] = {
            name: file.name,
            status: result.message === 'Duplicate detected' ? 'duplicate' : 'success',
            category: doc?.category || 'General',
            sub_category: doc?.sub_category || '',
            confidence: doc?.classification_confidence || 0,
            message: result.message === 'Duplicate detected'
              ? `Duplicate of existing document`
              : `Classified as ${doc?.category || 'General'}`,
          }
        } else {
          progress[i] = { name: file.name, status: 'error', message: result.detail || 'Upload failed' }
        }
      } catch (e) {
        progress[i] = { name: file.name, status: 'error', message: e.message }
      }
      setUploadProgress([...progress])
    }
    setUploading(false)
    fetchDocs()
  }, [])

  const handleDrag = (e) => { e.preventDefault(); e.stopPropagation() }
  const handleDragIn = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(true) }
  const handleDragOut = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(false) }
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setDragActive(false)
    handleFiles(e.dataTransfer.files)
  }

  async function handleDelete(docId) {
    if (!confirm('Delete this document?')) return
    try {
      await apiFetch(`/documents/${docId}`, { method: 'DELETE' })
      fetchDocs()
    } catch (e) { console.error(e) }
  }

  async function handleViewHistory(docId) {
    try {
      const data = await apiFetch(`/documents/${docId}/versions`)
      setVersionHistory(data)
      setShowHistoryModal(true)
    } catch (e) { console.error(e) }
  }

  // ── Filter logic ──
  const filtered = docs.filter(d => {
    const matchSearch = !search ||
      (d.original_filename || d.filename || '').toLowerCase().includes(search.toLowerCase()) ||
      (d.category || '').toLowerCase().includes(search.toLowerCase()) ||
      (d.tags || '').toLowerCase().includes(search.toLowerCase())
    const matchCat = !filterCategory || d.category === filterCategory
    const matchSrc = !filterSource || d.source === filterSource
    return matchSearch && matchCat && matchSrc
  })

  const categories = [...new Set(docs.map(d => d.category).filter(Boolean))]
  const sources = [...new Set(docs.map(d => d.source).filter(Boolean))]

  // ── Stats ──
  const totalDocs = docs.length
  const kbDocs = docs.filter(d => d.source === 'knowledge_base').length
  const adminDocs = docs.filter(d => d.source === 'admin_upload').length
  const agentDocs = docs.filter(d => d.source === 'agent_upload').length

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-heading)', margin: 0 }}>
            Document Intelligence Hub
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '4px 0 0' }}>
            Unified document management — auto-classified, indexed, and searchable
          </p>
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', borderRadius: 10, border: 'none',
            background: 'linear-gradient(135deg, #1e6bff, #06b6d4)',
            color: 'white', fontWeight: 600, fontSize: 14, cursor: 'pointer',
            boxShadow: '0 4px 15px rgba(30,107,255,0.3)',
            transition: 'transform 0.2s, box-shadow 0.2s',
          }}
          onMouseEnter={e => { e.target.style.transform = 'translateY(-1px)'; e.target.style.boxShadow = '0 6px 20px rgba(30,107,255,0.4)' }}
          onMouseLeave={e => { e.target.style.transform = ''; e.target.style.boxShadow = '0 4px 15px rgba(30,107,255,0.3)' }}
        >
          <Upload size={16} /> Upload Documents
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.txt,.xlsx,.pptx,.png,.jpg,.jpeg"
          style={{ display: 'none' }}
          onChange={e => handleFiles(e.target.files)}
        />
      </div>

      {/* Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Total Documents', value: totalDocs, icon: FileText, color: '#3b82f6' },
          { label: 'Knowledge Base', value: kbDocs, icon: Database, color: '#8b5cf6' },
          { label: 'Admin Uploads', value: adminDocs, icon: Shield, color: '#06b6d4' },
          { label: 'Agent Uploads', value: agentDocs, icon: Cpu, color: '#10b981' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} style={{
            background: 'var(--card-bg)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <div style={{
              width: 42, height: 42, borderRadius: 10,
              background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Icon size={20} color={color} />
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-heading)' }}>{value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Drag-and-Drop Zone */}
      <div
        onDragEnter={handleDragIn} onDragLeave={handleDragOut}
        onDragOver={handleDrag} onDrop={handleDrop}
        style={{
          border: `2px dashed ${dragActive ? '#1e6bff' : 'var(--border)'}`,
          borderRadius: 14, padding: dragActive ? '40px 32px' : '24px 32px',
          marginBottom: 24, textAlign: 'center', cursor: 'pointer',
          background: dragActive ? 'rgba(30,107,255,0.06)' : 'var(--card-bg)',
          transition: 'all 0.3s ease',
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <Zap size={28} color={dragActive ? '#1e6bff' : 'var(--text-secondary)'} style={{ marginBottom: 8 }} />
        <div style={{ fontSize: 14, fontWeight: 600, color: dragActive ? '#1e6bff' : 'var(--text-heading)' }}>
          {dragActive ? 'Drop files here to auto-classify & upload' : 'Drag & drop files here — AI auto-classifies on upload'}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
          PDF, DOCX, TXT, XLSX, PPTX, Images • No manual category needed
        </div>
      </div>

      {/* Upload Progress */}
      {uploadProgress.length > 0 && (
        <div style={{
          background: 'var(--card-bg)', border: '1px solid var(--border)',
          borderRadius: 12, padding: 16, marginBottom: 20,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)' }}>
              Upload Results
            </span>
            <button onClick={() => setUploadProgress([])}
              style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <X size={14} />
            </button>
          </div>
          {uploadProgress.map((p, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0',
              borderTop: i > 0 ? '1px solid var(--border)' : 'none',
            }}>
              {p.status === 'uploading' ? <Clock size={14} color="#f59e0b" /> :
                p.status === 'success' ? <CheckCircle size={14} color="#10b981" /> :
                  p.status === 'duplicate' ? <AlertTriangle size={14} color="#f59e0b" /> :
                    <AlertTriangle size={14} color="#ef4444" />}
              <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>{p.name}</span>
              {p.category && <CategoryBadge category={p.category} />}
              {p.confidence > 0 && <ConfidenceDot confidence={p.confidence} />}
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{p.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* Search + Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{
          flex: 1, minWidth: 250, display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--card-bg)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '0 14px',
        }}>
          <Search size={15} color="var(--text-secondary)" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search documents, categories, tags..."
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              color: 'var(--text-primary)', fontSize: 13, padding: '10px 0',
            }}
          />
          {search && <X size={14} color="var(--text-secondary)" style={{ cursor: 'pointer' }}
            onClick={() => setSearch('')} />}
        </div>
        <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)}
          style={{
            padding: '8px 14px', borderRadius: 10, fontSize: 13,
            background: 'var(--card-bg)', color: 'var(--text-primary)',
            border: '1px solid var(--border)', cursor: 'pointer',
          }}>
          <option value="">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
          style={{
            padding: '8px 14px', borderRadius: 10, fontSize: 13,
            background: 'var(--card-bg)', color: 'var(--text-primary)',
            border: '1px solid var(--border)', cursor: 'pointer',
          }}>
          <option value="">All Sources</option>
          {sources.map(s => <option key={s} value={s}>
            {SOURCE_LABELS[s]?.label || s}
          </option>)}
        </select>
        <button onClick={fetchDocs} title="Refresh"
          style={{
            padding: '8px 14px', borderRadius: 10, border: '1px solid var(--border)',
            background: 'var(--card-bg)', color: 'var(--text-secondary)',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13,
          }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Document Table */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
          Loading documents...
        </div>
      ) : filtered.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 60,
          background: 'var(--card-bg)', borderRadius: 14, border: '1px solid var(--border)',
        }}>
          <FileText size={40} color="var(--text-secondary)" style={{ marginBottom: 12, opacity: 0.4 }} />
          <div style={{ fontSize: 15, color: 'var(--text-secondary)' }}>
            {search || filterCategory || filterSource ? 'No documents match your filters' : 'No documents yet — upload some files to get started'}
          </div>
        </div>
      ) : (
        <div style={{
          background: 'var(--card-bg)', borderRadius: 14,
          border: '1px solid var(--border)', overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Document', 'Category', 'Source', 'Confidence', 'Size', 'Version', 'Actions'].map(h => (
                  <th key={h} style={{
                    padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600,
                    color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc, i) => (
                <tr key={doc.id || i} style={{
                  borderBottom: '1px solid var(--border)',
                  transition: 'background 0.15s',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(30,107,255,0.03)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <FileText size={16} color="var(--accent-blue)" />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)' }}>
                          {doc.original_filename || doc.filename}
                        </div>
                        {doc.sub_category && (
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                            {doc.sub_category}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <CategoryBadge category={doc.category} />
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <SourceBadge source={doc.source} />
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <ConfidenceDot confidence={doc.classification_confidence} />
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>
                    {doc.file_size ? `${(doc.file_size / 1024).toFixed(0)} KB` : '—'}
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>
                    v{doc.version || 1}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {doc.doc_group_id && (
                        <button onClick={() => handleViewHistory(doc.id)} title="Version History"
                          style={actionBtnStyle}>
                          <GitBranch size={13} />
                        </button>
                      )}
                      <button onClick={() => handleDelete(doc.id)} title="Delete"
                        style={{ ...actionBtnStyle, color: '#ef4444' }}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-secondary)', borderTop: '1px solid var(--border)' }}>
            Showing {filtered.length} of {totalDocs} documents
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {showHistoryModal && versionHistory && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000,
        }} onClick={() => setShowHistoryModal(false)}>
          <div style={{
            background: 'var(--card-bg)', borderRadius: 16, padding: 28,
            width: 500, maxHeight: '70vh', overflowY: 'auto',
            border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-heading)' }}>
                <GitBranch size={18} style={{ marginRight: 8 }} />Version History
              </h3>
              <button onClick={() => setShowHistoryModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>
            {(versionHistory.versions || []).map((v, i) => (
              <div key={v.id || i} style={{
                padding: '14px 16px', borderRadius: 10, marginBottom: 8,
                background: 'rgba(30,107,255,0.04)', border: '1px solid var(--border)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)' }}>
                    v{v.version} — {v.original_filename}
                  </span>
                  <CategoryBadge category={v.category} />
                </div>
                {v.version_notes && (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
                    {v.version_notes}
                  </div>
                )}
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {v.created_at ? new Date(v.created_at).toLocaleString() : ''} • {v.uploaded_by}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const actionBtnStyle = {
  background: 'none', border: '1px solid var(--border)', borderRadius: 6,
  padding: '5px 7px', cursor: 'pointer', color: 'var(--text-secondary)',
  display: 'flex', alignItems: 'center', transition: 'all 0.15s',
}
