import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../utils/api'
import { getToken } from '../utils/auth'
import {
  FileText, Upload, Download, Trash2, Search, Filter, X, GitBranch,
  CheckCircle, AlertTriangle, Clock, Database, Cpu, Shield, Tag,
  ChevronDown, RefreshCw, Layers, Zap, Eye, Folder, FolderPlus,
  ScanLine, RotateCcw, Calendar, CheckSquare, Square, ListTodo,
  Package, Printer, PanelLeftClose, PanelLeft, Plus
} from 'lucide-react'

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

const OCR_BADGES = {
  'completed': { label: 'OCR Done', color: '#10b981' },
  'processing': { label: 'OCR…', color: '#f59e0b' },
  'failed': { label: 'OCR Failed', color: '#ef4444' },
  'pending': { label: 'No OCR', color: '#6b7280' },
}

function CategoryBadge({ category }) {
  const c = CAT_COLORS[category] || CAT_COLORS['General']
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600, background: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
      <Tag size={10} />{category || 'General'}
    </span>
  )
}

function SourceBadge({ source }) {
  const s = SOURCE_LABELS[source] || SOURCE_LABELS['admin_upload']
  const Icon = s.icon
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 5, fontSize: 10, fontWeight: 600, background: `${s.color}15`, color: s.color }}>
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

function OcrBadge({ status }) {
  const b = OCR_BADGES[status] || OCR_BADGES['pending']
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: `${b.color}15`, color: b.color }}>
      <ScanLine size={10} />{b.label}
    </span>
  )
}

function ExpiryBadge({ date }) {
  if (!date) return null
  const daysLeft = Math.ceil((new Date(date) - new Date()) / (1000 * 60 * 60 * 24))
  const color = daysLeft < 0 ? '#ef4444' : daysLeft < 30 ? '#f59e0b' : '#10b981'
  const label = daysLeft < 0 ? 'Expired' : daysLeft < 30 ? `${daysLeft}d left` : `${daysLeft}d left`
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: `${color}15`, color }}>
      <Calendar size={10} />{label}
    </span>
  )
}

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [searchMode, setSearchMode] = useState('basic')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterExpiry, setFilterExpiry] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const [versionHistory, setVersionHistory] = useState(null)
  const [showHistoryModal, setShowHistoryModal] = useState(false)
  const [historyDocId, setHistoryDocId] = useState(null)
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [previewDoc, setPreviewDoc] = useState(null)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [showFolderPanel, setShowFolderPanel] = useState(true)
  const [folders, setFolders] = useState([])
  const [filterFolder, setFilterFolder] = useState(null)
  const [showCreateFolder, setShowCreateFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [showBulkCategorize, setShowBulkCategorize] = useState(false)
  const [bulkCategory, setBulkCategory] = useState('General')
  const [searchResults, setSearchResults] = useState(null)
  const [searchHighlights, setSearchHighlights] = useState({})
  const fileInputRef = useRef(null)
  const previewIframeRef = useRef(null)

  useEffect(() => { fetchDocs(); fetchFolders() }, [])

  async function fetchDocs() {
    setLoading(true)
    try {
      const data = await apiFetch('/documents/')
      const items = Array.isArray(data) ? data : (data?.documents || [])
      setDocs(items)
    } catch (e) { console.error('Fetch docs error:', e) }
    finally { setLoading(false) }
  }

  async function fetchFolders() {
    try {
      const data = await apiFetch('/documents/folders')
      if (data?.folders) setFolders(data.folders)
    } catch (e) { /* skip */ }
  }

  async function handleSearch() {
    if (!search.trim()) { setSearchResults(null); setSearchHighlights({}); return }
    try {
      const data = await apiFetch(`/documents/search?q=${encodeURIComponent(search)}`)
      if (data) {
        setSearchResults(data.results || [])
        setSearchHighlights(data.highlights || {})
      }
    } catch (e) { console.error(e) }
  }

  useEffect(() => {
    if (searchMode === 'fulltext' && search.trim().length >= 2) {
      const timer = setTimeout(handleSearch, 400)
      return () => clearTimeout(timer)
    }
    if (searchMode === 'fulltext' && !search.trim()) {
      setSearchResults(null)
      setSearchHighlights({})
    }
  }, [search, searchMode])

  const handleFiles = useCallback(async (files) => {
    if (!files || files.length === 0) return
    setUploading(true)
    const progress = Array.from(files).map(f => ({ name: f.name, status: 'uploading', category: null, message: 'Uploading...' }))
    setUploadProgress([...progress])
    const token = getToken()
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      try {
        const formData = new FormData()
        formData.append('file', file)
        const res = await fetch('/api/documents/upload', {
          method: 'POST',
          headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: formData
        })
        const result = await res.json()
        if (res.ok) {
          const doc = result.document || result.duplicate_of
          progress[i] = {
            name: file.name, status: result.message === 'Duplicate detected' ? 'duplicate' : 'success',
            category: doc?.category || 'General', sub_category: doc?.sub_category || '',
            confidence: doc?.classification_confidence || 0,
            message: result.message === 'Duplicate detected' ? 'Duplicate of existing document' : `Classified as ${doc?.category || 'General'}`,
          }
        } else {
          progress[i] = { name: file.name, status: 'error', message: result.detail || 'Upload failed' }
        }
      } catch (e) { progress[i] = { name: file.name, status: 'error', message: e.message } }
      setUploadProgress([...progress])
    }
    setUploading(false)
    fetchDocs()
  }, [])

  const handleDrag = (e) => { e.preventDefault(); e.stopPropagation() }
  const handleDragIn = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(true) }
  const handleDragOut = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(false) }
  const handleDrop = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(false); handleFiles(e.dataTransfer.files) }

  async function handleDelete(docId) {
    if (!confirm('Delete this document?')) return
    try { await apiFetch(`/documents/${docId}`, { method: 'DELETE' }); fetchDocs() }
    catch (e) { console.error(e) }
  }

  async function handleBulkDelete() {
    if (selectedIds.size === 0) return
    if (!confirm(`Delete ${selectedIds.size} document(s)?`)) return
    try {
      await apiFetch('/documents/bulk/delete', {
        method: 'POST',
        body: JSON.stringify({ doc_ids: [...selectedIds] })
      })
      setSelectedIds(new Set())
      fetchDocs()
    } catch (e) { console.error(e) }
  }

  async function handleBulkCategorize() {
    if (selectedIds.size === 0) return
    try {
      await apiFetch('/documents/bulk/categorize', {
        method: 'POST',
        body: JSON.stringify({ doc_ids: [...selectedIds], category: bulkCategory })
      })
      setSelectedIds(new Set())
      setShowBulkCategorize(false)
      fetchDocs()
    } catch (e) { console.error(e) }
  }

  async function handleViewHistory(docId) {
    try {
      const data = await apiFetch(`/documents/${docId}/versions`)
      setVersionHistory(data)
      setHistoryDocId(docId)
      setShowHistoryModal(true)
    } catch (e) { console.error(e) }
  }

  async function handleRollback(docId, versionId) {
    if (!confirm('Create a new version that rolls back to this version?')) return
    try {
      await apiFetch(`/documents/${docId}/rollback/${versionId}`, { method: 'POST' })
      setShowHistoryModal(false)
      fetchDocs()
    } catch (e) {
      console.error(e)
      alert('Rollback failed: ' + (e.message || 'Unknown error'))
    }
  }

  async function handleOcr(docId) {
    try {
      await apiFetch(`/documents/${docId}/ocr`, { method: 'POST' })
      fetchDocs()
    } catch (e) { console.error(e) }
  }

  async function handleCreateFolder() {
    if (!newFolderName.trim()) return
    try {
      await apiFetch('/documents/folders', {
        method: 'POST',
        body: JSON.stringify({ name: newFolderName.trim(), parent_id: filterFolder })
      })
      setNewFolderName('')
      setShowCreateFolder(false)
      fetchFolders()
    } catch (e) { console.error(e) }
  }

  async function handleDeleteFolder(folderId) {
    if (!confirm('Delete this folder? Documents inside will become unfiled.')) return
    try {
      await apiFetch(`/documents/folders/${folderId}`, { method: 'DELETE' })
      if (filterFolder === folderId) setFilterFolder(null)
      fetchFolders()
      fetchDocs()
    } catch (e) { console.error(e) }
  }

  async function handleSetFolder(docId, folderId) {
    try {
      await apiFetch(`/documents/${docId}`, {
        method: 'PUT',
        body: JSON.stringify({ folder_id: folderId || null })
      })
      fetchDocs()
    } catch (e) { console.error(e) }
  }

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === displayDocs.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(displayDocs.map(d => d.id)))
    }
  }

  const displayDocs = searchMode === 'fulltext' && searchResults ? searchResults : docs

  const filtered = displayDocs.filter(d => {
    const matchCat = !filterCategory || d.category === filterCategory
    const matchSrc = !filterSource || d.source === filterSource
    const matchFolder = !filterFolder || filterFolder === 'unfiled' ? !d.folder_id : d.folder_id === filterFolder
    const now = new Date()
    const matchExpiry = !filterExpiry ||
      (filterExpiry === 'expired' && d.expiry_date && new Date(d.expiry_date) < now) ||
      (filterExpiry === '30days' && d.expiry_date && new Date(d.expiry_date) < new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000) && new Date(d.expiry_date) >= now) ||
      (filterExpiry === 'none' && !d.expiry_date)
    return matchCat && matchSrc && matchFolder && matchExpiry
  })

  const categories = [...new Set(docs.map(d => d.category).filter(Boolean))]
  const sources = [...new Set(docs.map(d => d.source).filter(Boolean))]

  const totalDocs = docs.length
  const kbDocs = docs.filter(d => d.source === 'knowledge_base').length
  const adminDocs = docs.filter(d => d.source === 'admin_upload').length
  const agentDocs = docs.filter(d => d.source === 'agent_upload').length

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-heading)', margin: 0 }}>Document Intelligence Hub</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '4px 0 0' }}>Unified document management — auto-classified, indexed, and searchable</p>
        </div>
        <button onClick={() => fileInputRef.current?.click()}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #1e6bff, #06b6d4)', color: 'white', fontWeight: 600, fontSize: 14, cursor: 'pointer', boxShadow: '0 4px 15px rgba(30,107,255,0.3)', transition: 'transform 0.2s, box-shadow 0.2s' }}
          onMouseEnter={e => { e.target.style.transform = 'translateY(-1px)'; e.target.style.boxShadow = '0 6px 20px rgba(30,107,255,0.4)' }}
          onMouseLeave={e => { e.target.style.transform = ''; e.target.style.boxShadow = '0 4px 15px rgba(30,107,255,0.3)' }}
        >
          <Upload size={16} /> Upload Documents
        </button>
        <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.doc,.txt,.xlsx,.pptx,.png,.jpg,.jpeg" style={{ display: 'none' }} onChange={e => handleFiles(e.target.files)} />
      </div>

      {/* Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Total Documents', value: totalDocs, icon: FileText, color: '#3b82f6' },
          { label: 'Knowledge Base', value: kbDocs, icon: Database, color: '#8b5cf6' },
          { label: 'Admin Uploads', value: adminDocs, icon: Shield, color: '#06b6d4' },
          { label: 'Agent Uploads', value: agentDocs, icon: Cpu, color: '#10b981' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} style={{ background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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
      <div onDragEnter={handleDragIn} onDragLeave={handleDragOut} onDragOver={handleDrag} onDrop={handleDrop}
        style={{ border: `2px dashed ${dragActive ? '#1e6bff' : 'var(--border)'}`, borderRadius: 14, padding: dragActive ? '40px 32px' : '24px 32px', marginBottom: 24, textAlign: 'center', cursor: 'pointer', background: dragActive ? 'rgba(30,107,255,0.06)' : 'var(--card-bg)', transition: 'all 0.3s ease' }}
        onClick={() => fileInputRef.current?.click()}
      >
        <Zap size={28} color={dragActive ? '#1e6bff' : 'var(--text-secondary)'} style={{ marginBottom: 8 }} />
        <div style={{ fontSize: 14, fontWeight: 600, color: dragActive ? '#1e6bff' : 'var(--text-heading)' }}>
          {dragActive ? 'Drop files here to auto-classify & upload' : 'Drag & drop files here — AI auto-classifies on upload'}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>PDF, DOCX, TXT, XLSX, PPTX, Images • No manual category needed</div>
      </div>

      {/* Upload Progress */}
      {uploadProgress.length > 0 && (
        <div style={{ background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)' }}>Upload Results</span>
            <button onClick={() => setUploadProgress([])} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}><X size={14} /></button>
          </div>
          {uploadProgress.map((p, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderTop: i > 0 ? '1px solid var(--border)' : 'none' }}>
              {p.status === 'uploading' ? <Clock size={14} color="#f59e0b" /> :
                p.status === 'success' ? <CheckCircle size={14} color="#10b981" /> :
                  p.status === 'duplicate' ? <AlertTriangle size={14} color="#f59e0b" /> : <AlertTriangle size={14} color="#ef4444" />}
              <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>{p.name}</span>
              {p.category && <CategoryBadge category={p.category} />}
              {p.confidence > 0 && <ConfidenceDot confidence={p.confidence} />}
              <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{p.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* Search + Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 250, display: 'flex', alignItems: 'center', gap: 8, background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 10, padding: '0 14px' }}>
          <Search size={15} color="var(--text-secondary)" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={searchMode === 'fulltext' ? 'Full-text search with highlights...' : 'Search documents, categories, tags...'}
            style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', color: 'var(--text-primary)', fontSize: 13, padding: '10px 0' }}
          />
          {search && <X size={14} color="var(--text-secondary)" style={{ cursor: 'pointer' }} onClick={() => { setSearch(''); setSearchResults(null); setSearchHighlights({}) }} />}
        </div>
        <button onClick={() => setSearchMode(m => m === 'basic' ? 'fulltext' : 'basic')}
          style={{ padding: '8px 14px', borderRadius: 10, fontSize: 12, fontWeight: 600, border: `1px solid ${searchMode === 'fulltext' ? '#8b5cf6' : 'var(--border)'}`, background: searchMode === 'fulltext' ? 'rgba(139,92,246,0.12)' : 'var(--card-bg)', color: searchMode === 'fulltext' ? '#8b5cf6' : 'var(--text-secondary)', cursor: 'pointer' }}
        >
          {searchMode === 'fulltext' ? 'Full-Text' : 'Basic'}
        </button>
        <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)}
          style={{ padding: '8px 14px', borderRadius: 10, fontSize: 13, background: 'var(--card-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', cursor: 'pointer' }}>
          <option value="">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)}
          style={{ padding: '8px 14px', borderRadius: 10, fontSize: 13, background: 'var(--card-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', cursor: 'pointer' }}>
          <option value="">All Sources</option>
          {sources.map(s => <option key={s} value={s}>{SOURCE_LABELS[s]?.label || s}</option>)}
        </select>
        <select value={filterExpiry} onChange={e => setFilterExpiry(e.target.value)}
          style={{ padding: '8px 14px', borderRadius: 10, fontSize: 13, background: 'var(--card-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', cursor: 'pointer' }}>
          <option value="">All Expiry</option>
          <option value="expired">Expired</option>
          <option value="30days">Expires within 30 days</option>
          <option value="none">No expiry set</option>
        </select>
        <button onClick={() => { setShowFolderPanel(p => !p) }} title="Toggle Folder Panel"
          style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid var(--border)', background: showFolderPanel ? 'rgba(139,92,246,0.12)' : 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          {showFolderPanel ? <PanelLeftClose size={14} /> : <PanelLeft size={14} />} Folders
        </button>
        <button onClick={fetchDocs} title="Refresh"
          style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Batch Actions Bar */}
      {selectedIds.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', background: 'rgba(139,92,246,0.08)', borderRadius: 10, border: '1px solid rgba(139,92,246,0.2)', marginBottom: 16 }}>
          <CheckSquare size={16} color="#8b5cf6" />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)' }}>{selectedIds.size} selected</span>
          <button onClick={() => setSelectedIds(new Set())} style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12 }}>Clear</button>
          <div style={{ flex: 1 }} />
          <button onClick={() => setShowBulkCategorize(true)}
            style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: '#3b82f6', color: 'white', cursor: 'pointer', fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Tag size={12} /> Categorize
          </button>
          <button onClick={handleBulkDelete}
            style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: '#ef4444', color: 'white', cursor: 'pointer', fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Trash2 size={12} /> Delete
          </button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 20 }}>
        {/* Folder Sidebar */}
        {showFolderPanel && (
          <div style={{ width: 220, flexShrink: 0 }}>
            <div style={{ background: 'var(--card-bg)', borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
              <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Folders</span>
                <button onClick={() => setShowCreateFolder(true)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', padding: 2 }}><FolderPlus size={14} /></button>
              </div>
              <div style={{ padding: 6 }}>
                <FolderItem
                  name="All Documents"
                  icon={Folder}
                  active={filterFolder === null}
                  count={totalDocs}
                  onClick={() => setFilterFolder(null)}
                />
                <FolderItem
                  name="Unfiled"
                  icon={Package}
                  active={filterFolder === 'unfiled'}
                  count={docs.filter(d => !d.folder_id).length}
                  onClick={() => setFilterFolder('unfiled')}
                />
                {folders.map(f => (
                  <div key={f.id} style={{ paddingLeft: f.parent_id ? 20 : 0 }}>
                    <FolderItem
                      name={f.name}
                      icon={Folder}
                      color={f.color}
                      active={filterFolder === f.id}
                      count={f.document_count}
                      onClick={() => setFilterFolder(f.id)}
                      onDelete={() => handleDeleteFolder(f.id)}
                    />
                  </div>
                ))}
              </div>
            </div>
            {/* Create Folder Inline */}
            {showCreateFolder && (
              <div style={{ marginTop: 8, background: 'var(--card-bg)', borderRadius: 10, border: '1px solid var(--border)', padding: 12 }}>
                <input value={newFolderName} onChange={e => setNewFolderName(e.target.value)} placeholder="Folder name"
                  style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', fontSize: 12, marginBottom: 8, boxSizing: 'border-box' }}
                  onKeyDown={e => e.key === 'Enter' && handleCreateFolder()}
                />
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={handleCreateFolder} style={{ flex: 1, padding: '6px 0', borderRadius: 6, border: 'none', background: '#8b5cf6', color: 'white', cursor: 'pointer', fontSize: 11, fontWeight: 600 }}>Create</button>
                  <button onClick={() => { setShowCreateFolder(false); setNewFolderName('') }} style={{ flex: 1, padding: '6px 0', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 11 }}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Main Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>Loading documents...</div>
          ) : filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 60, background: 'var(--card-bg)', borderRadius: 14, border: '1px solid var(--border)' }}>
              <FileText size={40} color="var(--text-secondary)" style={{ marginBottom: 12, opacity: 0.4 }} />
              <div style={{ fontSize: 15, color: 'var(--text-secondary)' }}>
                {search || filterCategory || filterSource || filterExpiry || filterFolder ? 'No documents match your filters' : 'No documents yet — upload some files to get started'}
              </div>
            </div>
          ) : (
            <div style={{ background: 'var(--card-bg)', borderRadius: 14, border: '1px solid var(--border)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '12px 10px', textAlign: 'center', width: 36 }}>
                      <div style={{ cursor: 'pointer' }} onClick={toggleSelectAll}>
                        {selectedIds.size === displayDocs.length ? <CheckSquare size={14} color="#8b5cf6" /> : <Square size={14} color="var(--text-secondary)" />}
                      </div>
                    </th>
                    {['Document', 'Category', 'Source', 'OCR', 'Expiry', 'Confidence', 'Size', 'Version', 'Actions'].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((doc, i) => {
                    const hl = searchHighlights[doc.id] || {}
                    return (
                      <tr key={doc.id || i} style={{ borderBottom: '1px solid var(--border)', transition: 'background 0.15s' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'rgba(30,107,255,0.03)'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}
                      >
                        <td style={{ padding: '12px 10px', textAlign: 'center' }}>
                          <div style={{ cursor: 'pointer' }} onClick={() => toggleSelect(doc.id)}>
                            {selectedIds.has(doc.id) ? <CheckSquare size={14} color="#8b5cf6" /> : <Square size={14} color="var(--text-secondary)" />}
                          </div>
                        </td>
                        <td style={{ padding: '12px 16px', maxWidth: 280 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <FileText size={16} color="var(--accent-blue)" />
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)', wordBreak: 'break-word' }}
                                dangerouslySetInnerHTML={hl.filename ? { __html: hl.filename } : undefined}>
                                {!hl.filename ? (doc.original_filename || doc.filename) : undefined}
                              </div>
                              {doc.sub_category && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{doc.sub_category}</div>}
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: '12px 16px' }}><CategoryBadge category={doc.category} /></td>
                        <td style={{ padding: '12px 16px' }}><SourceBadge source={doc.source} /></td>
                        <td style={{ padding: '12px 16px' }}><OcrBadge status={doc.ocr_status} /></td>
                        <td style={{ padding: '12px 16px' }}><ExpiryBadge date={doc.expiry_date} /></td>
                        <td style={{ padding: '12px 16px' }}><ConfidenceDot confidence={doc.classification_confidence} /></td>
                        <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>{doc.file_size ? `${(doc.file_size / 1024).toFixed(0)} KB` : '—'}</td>
                        <td style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>v{doc.version || 1}</td>
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button onClick={() => { setPreviewDoc(doc); setShowPreviewModal(true) }} title="Preview" style={actionBtnStyle}><Eye size={13} /></button>
                            {doc.ocr_status !== 'completed' && (
                              <button onClick={() => handleOcr(doc.id)} title="Run OCR" style={{ ...actionBtnStyle, color: '#8b5cf6' }}><ScanLine size={13} /></button>
                            )}
                            {doc.doc_group_id && (
                              <button onClick={() => handleViewHistory(doc.id)} title="Version History" style={actionBtnStyle}><GitBranch size={13} /></button>
                            )}
                            <div style={{ position: 'relative' }}>
                              <select onChange={e => { if (e.target.value) handleSetFolder(doc.id, parseInt(e.target.value)); e.target.value = '' }}
                                style={{ ...actionBtnStyle, appearance: 'none', padding: '5px 7px', fontSize: 0, cursor: 'pointer', color: 'var(--text-secondary)' }}
                                title="Move to folder"
                              >
                                <option value="">—</option>
                                {folders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                                <option value="">Unfile</option>
                              </select>
                              <Folder size={13} style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', pointerEvents: 'none', color: 'var(--text-secondary)' }} />
                            </div>
                            <button onClick={() => handleDelete(doc.id)} title="Delete" style={{ ...actionBtnStyle, color: '#ef4444' }}><Trash2 size={13} /></button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-secondary)', borderTop: '1px solid var(--border)' }}>
                Showing {filtered.length} of {displayDocs.length} documents
                {searchMode === 'fulltext' && searchResults && ` (full-text search results)`}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* PDF Preview Modal */}
      {showPreviewModal && previewDoc && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000 }}
          onClick={() => setShowPreviewModal(false)}>
          <div style={{ width: '90vw', height: '90vh', background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <FileText size={18} color="var(--accent-blue)" />
                <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-heading)' }}>{previewDoc.original_filename || previewDoc.filename}</span>
                <CategoryBadge category={previewDoc.category} />
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <a href={`/api/documents/${previewDoc.id}/download`} download
                  style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', cursor: 'pointer', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <Download size={14} /> Download
                </a>
                <button onClick={() => setShowPreviewModal(false)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}><X size={20} /></button>
              </div>
            </div>
            <div style={{ flex: 1, background: '#1a1a2e' }}>
              {previewDoc.file_type === 'pdf' ? (
                <iframe ref={previewIframeRef} src={`/api/documents/${previewDoc.id}/download`} style={{ width: '100%', height: '100%', border: 'none' }} title="PDF Preview" />
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
                  <div style={{ textAlign: 'center' }}>
                    <FileText size={48} style={{ marginBottom: 16, opacity: 0.4 }} />
                    <p>Preview not available for {previewDoc.file_type?.toUpperCase()} files</p>
                    <a href={`/api/documents/${previewDoc.id}/download`} download
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 20px', borderRadius: 8, border: 'none', background: 'var(--primary)', color: 'white', cursor: 'pointer', textDecoration: 'none', fontSize: 14, marginTop: 12 }}>
                      <Download size={16} /> Download File
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {showHistoryModal && versionHistory && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setShowHistoryModal(false)}>
          <div style={{ background: 'var(--card-bg)', borderRadius: 16, padding: 28, width: 560, maxHeight: '75vh', overflowY: 'auto', border: '1px solid var(--border)', boxShadow: 'var(--shadow-lg)' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 18, color: 'var(--text-heading)' }}><GitBranch size={18} style={{ marginRight: 8 }} />Version History</h3>
              <button onClick={() => setShowHistoryModal(false)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}><X size={18} /></button>
            </div>
            {(versionHistory.versions || []).map((v, i) => {
              const isLatest = i === 0
              return (
                <div key={v.id || i} style={{ padding: '14px 16px', borderRadius: 10, marginBottom: 8, background: 'rgba(30,107,255,0.04)', border: '1px solid var(--border)', position: 'relative' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-heading)' }}>v{v.version} — {v.original_filename}</span>
                      {isLatest && <span style={{ marginLeft: 8, padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: 'rgba(16,185,129,0.12)', color: '#10b981' }}>Latest</span>}
                    </div>
                    <CategoryBadge category={v.category} />
                  </div>
                  {v.version_notes && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>{v.version_notes}</div>}
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>{v.created_at ? new Date(v.created_at).toLocaleString() : ''} • {v.uploaded_by}</span>
                    {!isLatest && (
                      <button onClick={() => handleRollback(historyDocId, v.id)}
                        style={{ padding: '4px 10px', borderRadius: 5, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: '#8b5cf6', cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <RotateCcw size={11} /> Rollback
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Bulk Categorize Modal */}
      {showBulkCategorize && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100 }}
          onClick={() => setShowBulkCategorize(false)}>
          <div style={{ width: 400, background: 'var(--card-bg)', borderRadius: 16, padding: 24, border: '1px solid var(--border)' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 16px', fontSize: 18, color: 'var(--text-heading)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Tag size={18} /> Categorize {selectedIds.size} Document(s)
            </h3>
            <select value={bulkCategory} onChange={e => setBulkCategory(e.target.value)}
              style={{ width: '100%', padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-primary)', fontSize: 14, marginBottom: 20 }}>
              {Object.keys(CAT_COLORS).map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowBulkCategorize(false)}
                style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 14 }}>Cancel</button>
              <button onClick={handleBulkCategorize}
                style={{ flex: 1, padding: 12, borderRadius: 8, border: 'none', background: 'var(--primary)', color: 'white', cursor: 'pointer', fontSize: 14, fontWeight: 600 }}>Apply</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function FolderItem({ name, icon: Icon, color, active, count, onClick, onDelete }) {
  return (
    <div onClick={onClick}
      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: active ? 600 : 400, background: active ? 'rgba(139,92,246,0.1)' : 'transparent', color: active ? '#8b5cf6' : 'var(--text-primary)', transition: 'all 0.15s' }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-surface)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      <Icon size={14} color={color || (active ? '#8b5cf6' : 'var(--text-secondary)')} />
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', background: 'var(--bg-surface)', padding: '1px 6px', borderRadius: 8 }}>{count}</span>
      {onDelete && (
        <button onClick={e => { e.stopPropagation(); onDelete() }}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 2, opacity: 0, transition: 'opacity 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.opacity = '1'}
          onMouseLeave={e => e.currentTarget.style.opacity = '0'}
        ><X size={11} /></button>
      )}
    </div>
  )
}

const actionBtnStyle = {
  background: 'none', border: '1px solid var(--border)', borderRadius: 6,
  padding: '5px 7px', cursor: 'pointer', color: 'var(--text-secondary)',
  display: 'flex', alignItems: 'center', transition: 'all 0.15s',
}
