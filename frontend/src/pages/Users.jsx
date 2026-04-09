import { useState, useEffect } from 'react'
import { getToken, logout } from '../utils/auth'
import { UserPlus, Search, Filter, MoreVertical, UserCheck, UserX } from 'lucide-react'

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

export default function Users() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchUsers()
  }, [])

  async function fetchUsers() {
    setLoading(true)
    try {
      const data = await apiFetch('/users/')
      setUsers(Array.isArray(data) ? data : (data?.items || []))
    } catch (e) {
      console.error('Fetch users error:', e)
    } finally {
      setLoading(false)
    }
  }

  const filteredUsers = users.filter(u => 
    u.username?.toLowerCase().includes(search.toLowerCase()) || 
    u.email?.toLowerCase().includes(search.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(search.toLowerCase())
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
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#fff' }}>User Management</h1>
          <p style={{ color: '#7a90b8', margin: '4px 0 0', fontSize: '14px' }}>Manage system administrators and operators</p>
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
          <UserPlus size={18} />
          Add User
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
              placeholder="Search by name, email or username..."
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
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>USER</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>ROLE</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>STATUS</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}>LAST LOGIN</th>
                <th style={{ padding: '16px 20px', color: '#4a5e8a', fontSize: '13px', fontWeight: 600 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan=\"5\" style={{ padding: '40px', textAlign: 'center', color: '#7a90b8' }}>Loading users...</td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan=\"5\" style={{ padding: '40px', textAlign: 'center', color: '#7a90b8' }}>No users found.</td>
                </tr>
              ) : (
                filteredUsers.map((user, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.03)' }}>
                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                          width: '36px',
                          height: '36px',
                          borderRadius: '50%',
                          background: 'linear-gradient(135deg, #1e6bff 0%, #00c8e0 100%)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 700,
                          fontSize: '14px',
                          color: '#fff'
                        }}>
                          {(user.full_name || user.username || 'U')[0].toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, color: '#fff', fontSize: '14px' }}>{user.full_name || user.username}</div>
                          <div style={{ fontSize: '12px', color: '#4a5e8a' }}>{user.email}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{ 
                        padding: '4px 10px', 
                        borderRadius: '6px', 
                        background: 'rgba(36, 99, 255, 0.1)', 
                        color: '#7ab4ff',
                        fontSize: '12px',
                        fontWeight: 600
                      }}>
                        {user.role || 'Super Admin'}
                      </span>
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {user.is_active !== false ? (
                          <>
                            <UserCheck size={14} color="#22c55e" />
                            <span style={{ color: '#22c55e', fontSize: '13px' }}>Active</span>
                          </>
                        ) : (
                          <>
                            <UserX size={14} color="#ef4444" />
                            <span style={{ color: '#ef4444', fontSize: '13px' }}>Inactive</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '16px 20px', color: '#7a90b8', fontSize: '13px' }}>
                      {user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}
                    </td>
                    <td style={{ padding: '16px 20px', textAlign: 'right' }}>
                      <button style={{ background: 'none', border: 'none', color: '#4a5e8a', cursor: 'pointer' }}>
                        <MoreVertical size={18} />
                      </button>
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
