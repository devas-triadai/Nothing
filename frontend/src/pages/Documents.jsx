import { useState, useEffect } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import { getToken } from '../utils/auth'
import { FileText, Upload, Download, Trash2, Eye, History, Search, Filter, MoreVertical, X, GitBranch } from 'lucide-react'

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadData, setUploadData] = useState({
    category: '',
    description: '',
    version_notes: ''
  })
  const [versionHistory, setVersionHistory] = useState(null)
  const [showHistoryModal, setShowHistoryModal] = useState(false)

  useEffect(() => {
    fetchDocs()
  }, [])

  async function fetchDocs() {
    setLoading(true)
    try {
      const data = await apiFetch('/documents/')
      setDocs(Array.isArray(data) ? data : (data?.documents || data?.items || []))
    } catch (e) {
      console.error('Fetch docs error:', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload() {
    if (!selectedFile) {
      alert('Please select a file')
      return
    }
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('category', uploadData.category)
      formData.append('description', uploadData.description)
      formData.append('version_notes', uploadData.version_notes)

      const token = getToken()
      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: formData
      })

      if (res.ok) {
        setShowUploadModal(false)
        setSelectedFile(null)
        setUploadData({ category: '', description: '', version_notes: '' })
        fetchDocs()
      } else {
        alert('Failed to upload file')
      }
    } catch (e) {
      console.error('Upload error:', e)
      alert('Failed to upload file')
    }
  }

  async function handleView(doc) {
    const token = getToken()
    window.open(`/api/documents/${doc.id}/download?token=${token}`, '_blank')
  }

  async function handleDownload(doc) {
    try {
      const token = getToken()
      const res = await fetch(`/api/documents/${doc.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      })
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = doc.original_filename || doc.filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Download error:', e)
      alert('Failed to download file')
    }
  }

  async function handleHistory(doc) {
    try {
      const data = await apiFetch(`/documents/${doc.id}/versions`)
      setVersionHistory({ doc, versions: data?.versions || [] })
      setShowHistoryModal(true)
    } catch (e) {
      console.error('History error:', e)
      alert('Failed to fetch version history')
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Are you sure you want to delete "${doc.original_filename || doc.filename}"? This cannot be undone.`)) return
    try {
      await apiFetch(`/documents/${doc.id}`, { method: 'DELETE' })
      setDocs(prev => prev.filter(d => d.id !== doc.id))
    } catch (e) {
      console.error('Delete error:', e)
      alert('Failed to delete document')
    }
  }

  const filteredDocs = docs.filter(d => {
    const q = search.toLowerCase()
    if (!q) return true
    return d.filename?.toLowerCase().includes(q) || 
      d.original_filename?.toLowerCase().includes(q) ||
      d.category?.toLowerCase().includes(q) ||
      d.tags?.toLowerCase().includes(q) ||
      d.file_type?.toLowerCase().includes(q)
  })

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: '32px' 
      }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: 'var(--text-heading)' }}>Document Knowledge Base</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: '14px' }}>Manage files used for RAG and agent training</p>
        </div>
        <button onClick={() => setShowUploadModal(true)} style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 18px',
          background: 'var(--accent-blue)',
          color: 'var(--text-heading)',
          border: 'none',
          borderRadius: '10px',
          fontWeight: 600,
          cursor: 'pointer',
          fontSize: '14px'
        }}>
          <Upload size={18} />
          Upload Files
        </button>
      </div>

      <div style={{
        background: 'var(--card-bg)',
        border: '1px solid var(--card-border)',
        borderRadius: '16px',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '20px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          gap: '16px'
        }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={18} style={{ 
              position: 'absolute', 
              left: '14px', 
              top: '50%', 
              transform: 'translateY(-50%)', 
              color: 'var(--text-muted)' 
            }} />
            <input
              type="text"
              placeholder="Search documents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px 10px 42px',
                background: 'var(--card-bg)',
                border: '1px solid var(--card-border)',
                borderRadius: '8px',
                color: 'var(--text-heading)',
                fontSize: '14px',
                outline: 'none'
              }}
            />
          </div>
          <button style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 16px',
            background: 'var(--card-bg)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--card-border)',
            borderRadius: '8px',
            cursor: 'pointer'
          }}>
            <Filter size={18} />
            Filter
          </button>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '13px', fontWeight: 600 }}>FILENAME</th>
                <th style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '13px', fontWeight: 600 }}>CATEGORY</th>
                <th style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '13px', fontWeight: 600 }}>VERSION</th>
                <th style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '13px', fontWeight: 600 }}>UPLOADED BY</th>
                <th style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '13px', fontWeight: 600 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="5" style={{ padding: '40px', textAlign: 'center' }}><Spinner size={28} /></td>
                </tr>
              ) : filteredDocs.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>No documents found.</td>
                </tr>
              ) : (
                filteredDocs.map((doc, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '8px',
                          background: 'rgba(36, 99, 255, 0.1)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#7ab4ff'
                        }}>
                          <FileText size={20} />
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, color: 'var(--text-heading)', fontSize: '14px' }}>{doc.filename}</div>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{doc.type || 'PDF'} • {new Date(doc.created_at).toLocaleDateString()}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '16px 20px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        background: doc.category === 'Global Standard' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(74, 139, 255, 0.1)',
                        color: doc.category === 'Global Standard' ? '#22c55e' : '#7ab4ff',
                        fontSize: '11px',
                        fontWeight: 600
                      }}>
                        {doc.category || 'Uncategorised'}
                      </span>
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{ 
                        padding: '4px 8px', 
                        borderRadius: '4px', 
                        background: 'var(--bg-secondary)', 
                        color: 'var(--text-primary)',
                        fontSize: '11px',
                        fontWeight: 600
                      }}>
                        v{doc.version || '1.0'}
                      </span>
                    </td>
                    <td style={{ padding: '16px 20px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                      {doc.uploaded_by || 'System'}
                    </td>
                    <td style={{ padding: '16px 20px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                        <button onClick={() => handleView(doc)} title="View" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><Eye size={18} /></button>
                        <button onClick={() => handleDownload(doc)} title="Download" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><Download size={18} /></button>
                        <button onClick={() => handleHistory(doc)} title="History" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><History size={18} /></button>
                        <button onClick={() => handleDelete(doc)} title="Delete" style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', opacity: 0.7 }}><Trash2 size={18} /></button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showUploadModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '16px',
            padding: '32px',
            width: '90%',
            maxWidth: '500px'
          }}>
            <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-heading)', margin: '0 0 24px' }}>Upload Document</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{
                padding: '24px',
                border: '2px dashed var(--border)',
                borderRadius: '12px',
                textAlign: 'center',
                cursor: 'pointer'
              }} onClick={() => document.getElementById('fileInput').click()}>
                <Upload size={32} style={{ color: '#7ab4ff', marginBottom: '12px' }} />
                <p style={{ color: 'var(--text-secondary)', fontSize: '14px', margin: 0 }}>
                  {selectedFile ? selectedFile.name : 'Click to select file'}
                </p>
                <input
                  id="fileInput"
                  type="file"
                  style={{ display: 'none' }}
                  onChange={(e) => setSelectedFile(e.target.files[0])}
                />
              </div>
              <select
                value={uploadData.category}
                onChange={(e) => setUploadData({...uploadData, category: e.target.value})}
                style={{
                  padding: '12px 16px',
                  background: 'var(--bg-input, var(--surface))',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  color: 'var(--text-heading)',
                  fontSize: '14px',
                  outline: 'none',
                  appearance: 'none'
                }}
              >
                <option value="" disabled>Select Category</option>
                <option value="Standard">Standard / Specification</option>
                <option value="Blueprint">Blueprint / Drawing</option>
                <option value="SOP">SOP / Procedure</option>
                <option value="Report">Report / Assessment</option>
                <option value="Bid Document">Bid / Tender Document</option>
                <option value="Vessel Document">Vessel / Ship Document</option>
                <option value="Compliance">Compliance / Regulatory</option>
                <option value="Imagery">Imagery / Scan</option>
                <option value="General">General</option>
              </select>
              <textarea
                placeholder="Description (optional)"
                value={uploadData.description}
                onChange={(e) => setUploadData({...uploadData, description: e.target.value})}
                rows={3}
                style={{
                  padding: '12px 16px',
                  background: 'var(--bg-input, var(--surface))',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  color: 'var(--text-heading)',
                  fontSize: '14px',
                  outline: 'none',
                  resize: 'none'
                }}
              />
              <input
                placeholder="Version notes (optional)"
                value={uploadData.version_notes}
                onChange={(e) => setUploadData({...uploadData, version_notes: e.target.value})}
                style={{
                  padding: '12px 16px',
                  background: 'var(--bg-input, var(--surface))',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  color: 'var(--text-heading)',
                  fontSize: '14px',
                  outline: 'none'
                }}
              />
              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <button
                  onClick={handleUpload}
                  style={{
                    flex: 1,
                    padding: '12px',
                    background: 'var(--accent-blue)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '14px'
                  }}
                >
                  Upload
                </button>
                <button
                  onClick={() => {
                    setShowUploadModal(false)
                    setSelectedFile(null)
                    setUploadData({ category: '', description: '', version_notes: '' })
                  }}
                  style={{
                    flex: 1,
                    padding: '12px',
                    background: 'var(--bg-secondary, var(--surface))',
                    color: 'var(--text-heading)',
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '14px'
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {showHistoryModal && versionHistory && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'var(--card-bg, var(--surface))',
            border: '1px solid var(--border)',
            borderRadius: '16px',
            padding: '32px',
            width: '90%',
            maxWidth: '600px',
            maxHeight: '80vh',
            overflow: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <GitBranch size={20} color="var(--accent-blue, #1e6bff)" />
                <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-heading)', margin: 0 }}>
                  Version History
                </h2>
              </div>
              <button
                onClick={() => { setShowHistoryModal(false); setVersionHistory(null); }}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
              Lineage for: <strong style={{ color: 'var(--text-heading)' }}>{versionHistory.doc.original_filename || versionHistory.doc.filename}</strong>
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
              {versionHistory.versions.map((v, i) => (
                <div key={v.id} style={{ display: 'flex', gap: '16px', position: 'relative' }}>
                  {/* Timeline line */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '24px', flexShrink: 0 }}>
                    <div style={{
                      width: '12px', height: '12px', borderRadius: '50%',
                      background: v.id === versionHistory.doc.id ? 'var(--accent-blue, #1e6bff)' : 'var(--border)',
                      border: v.id === versionHistory.doc.id ? '2px solid var(--accent-blue, #1e6bff)' : '2px solid var(--text-muted)',
                      zIndex: 1
                    }} />
                    {i < versionHistory.versions.length - 1 && (
                      <div style={{ width: '2px', flex: 1, background: 'var(--border)', minHeight: '40px' }} />
                    )}
                  </div>
                  {/* Version details */}
                  <div style={{
                    flex: 1, padding: '10px 14px', marginBottom: '8px', borderRadius: '10px',
                    background: v.id === versionHistory.doc.id ? 'rgba(30, 107, 255, 0.08)' : 'transparent',
                    border: v.id === versionHistory.doc.id ? '1px solid rgba(30, 107, 255, 0.2)' : '1px solid var(--border)',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-heading)' }}>
                        v{v.version} {v.id === versionHistory.doc.id ? '(current)' : ''}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {v.created_at ? new Date(v.created_at).toLocaleDateString() : ''}
                      </span>
                    </div>
                    {v.version_notes && (
                      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0' }}>
                        {v.version_notes}
                      </p>
                    )}
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', margin: '4px 0 0' }}>
                      Uploaded by: {v.uploaded_by || 'System'} • {v.file_type?.toUpperCase()} • {((v.file_size || 0) / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
