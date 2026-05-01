import { useState, useEffect } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import { getToken } from '../utils/auth'
import { FileText, Upload, Download, Trash2, Eye, History, Search, Filter, MoreVertical } from 'lucide-react'

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

  useEffect(() => {
    fetchDocs()
  }, [])

  async function fetchDocs() {
    setLoading(true)
    try {
      const data = await apiFetch('/documents/')
      setDocs(Array.isArray(data) ? data : (data?.items || []))
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

  const filteredDocs = docs.filter(d => 
    d.filename?.toLowerCase().includes(search.toLowerCase()) || 
    d.type?.toLowerCase().includes(search.toLowerCase())
  )

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
                <th style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '13px', fontWeight: 600 }}>SIZE</th>
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
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.03)' }}>
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
                      {doc.size ? (doc.size / 1024 / 1024).toFixed(2) + ' MB' : '0.5 MB'}
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{ 
                        padding: '4px 8px', 
                        borderRadius: '4px', 
                        background: 'rgba(255, 255, 255, 0.05)', 
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
                        <button title="View" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><Eye size={18} /></button>
                        <button title="Download" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><Download size={18} /></button>
                        <button title="History" style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}><History size={18} /></button>
                        <button title="Delete" style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', opacity: 0.7 }}><Trash2 size={18} /></button>
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
            background: '#1a1f2e',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '16px',
            padding: '32px',
            width: '90%',
            maxWidth: '500px'
          }}>
            <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-heading)', margin: '0 0 24px' }}>Upload Document</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{
                padding: '24px',
                border: '2px dashed rgba(255, 255, 255, 0.2)',
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
              <input
                placeholder="Category (optional)"
                value={uploadData.category}
                onChange={(e) => setUploadData({...uploadData, category: e.target.value})}
                style={{
                  padding: '12px 16px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '8px',
                  color: 'var(--text-heading)',
                  fontSize: '14px',
                  outline: 'none'
                }}
              />
              <textarea
                placeholder="Description (optional)"
                value={uploadData.description}
                onChange={(e) => setUploadData({...uploadData, description: e.target.value})}
                rows={3}
                style={{
                  padding: '12px 16px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
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
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
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
                    color: 'var(--text-heading)',
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
                    background: 'rgba(255, 255, 255, 0.1)',
                    color: 'var(--text-heading)',
                    border: 'none',
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
    </div>
  )
}
