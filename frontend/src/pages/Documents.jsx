import { useState, useEffect } from 'react'
import { getToken, logout } from '../utils/auth'
import { FileText, Upload, Download, Trash2, Eye, History, Search, Filter, MoreVertical } from 'lucide-react'

const API = '/api'

async function apiFetch(path, opts = {}) {
  const token = getToken()
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {})
    }
  })
  if (res.status === 401) {
    logout()
    return null
  }
  return res.json().catch(() => null)
}

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

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
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#fff' }}>Document Knowledge Base</h1>
          <p style={{ color: '#7a90b8', margin: '4px 0 0', fontSize: '14px' }}>Manage files used for RAG and agent training</p>
        </div>
        <button style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 18px',
          background: '#2463ff',
          color: '#fff',
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
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        borderRadius: '16px',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: '20px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          display: 'flex',
          gap: '16px'
        }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={18} style={{ 
              position: 'absolute', 
              left: '14px', 
              top: '50%', 
              transform: 'translateY(-50%)', 
              color: '#4a5e8a' 
            }} />
            <input
              type="text"
              placeholder="Search documents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px 10px 42px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                borderRadius: '8px',
                color: '#fff',
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
            background: 'rgba(255, 255, 255, 0.03)',
            color: '#7a90b8',
            border: '1px solid rgba(255, 255, 255, 0.05)',
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
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>FILENAME</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>SIZE</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>VERSION</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>UPLOADED BY</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="5" style={{ padding: '40px', textAlign: 'center', color: '#7a90b8' }}>Loading documents...</td>
                </tr>
              ) : filteredDocs.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ padding: '40px', textAlign: 'center', color: '#7a90b8' }}>No documents found.</td>
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
                          <div style={{ fontWeight: 600, color: '#fff', fontSize: '14px' }}>{doc.filename}</div>
                          <div style={{ fontSize: '12px', color: '#4a5e8a' }}>{doc.type || 'PDF'} • {new Date(doc.created_at).toLocaleDateString()}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '16px 20px', color: '#7a90b8', fontSize: '13px' }}>
                      {doc.size ? (doc.size / 1024 / 1024).toFixed(2) + ' MB' : '0.5 MB'}
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{ 
                        padding: '4px 8px', 
                        borderRadius: '4px', 
                        background: 'rgba(255, 255, 255, 0.05)', 
                        color: '#c8d8f0',
                        fontSize: '11px',
                        fontWeight: 600
                      }}>
                        v{doc.version || '1.0'}
                      </span>
                    </td>
                    <td style={{ padding: '16px 20px', color: '#7a90b8', fontSize: '13px' }}>
                      {doc.uploaded_by || 'System'}
                    </td>
                    <td style={{ padding: '16px 20px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                        <button title="View" style={{ background: 'none', border: 'none', color: '#4a5e8a', cursor: 'pointer' }}><Eye size={18} /></button>
                        <button title="Download" style={{ background: 'none', border: 'none', color: '#4a5e8a', cursor: 'pointer' }}><Download size={18} /></button>
                        <button title="History" style={{ background: 'none', border: 'none', color: '#4a5e8a', cursor: 'pointer' }}><History size={18} /></button>
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
    </div>
  )
}
