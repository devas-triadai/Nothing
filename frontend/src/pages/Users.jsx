import { useState, useEffect } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import { UserPlus, Search, Edit2, Trash2, UserCheck, UserX, RefreshCw, Shield, Eye } from 'lucide-react'

export default function Users() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [editUser, setEditUser] = useState(null)   // user object being edited
  const [toast, setToast] = useState(null)          // { type: 'success'|'error', msg }
  const [newUser, setNewUser] = useState({
    username: '',
    email: '',
    full_name: '',
    password: '',
    role: 'viewer',
    department: '',
    rank: '',
    service_number: '',
  })

  useEffect(() => { fetchUsers() }, [])

  function showToast(type, msg) {
    setToast({ type, msg })
    setTimeout(() => setToast(null), 3500)
  }

  async function fetchUsers() {
    setLoading(true)
    try {
      // Backend returns { total: N, users: [...] }
      const data = await apiFetch('/users/')
      if (data?.users) {
        setUsers(data.users)
        setTotal(data.total || data.users.length)
      } else if (Array.isArray(data)) {
        setUsers(data)
        setTotal(data.length)
      } else {
        setUsers([])
        setTotal(0)
      }
    } catch (e) {
      console.error('Fetch users error:', e)
      showToast('error', 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  async function handleAddUser() {
    if (!newUser.username || !newUser.email || !newUser.full_name || !newUser.password) {
      showToast('error', 'Username, email, full name and password are required')
      return
    }
    try {
      // Convert empty optional strings to null to avoid SQLite unique constraint issues
      const payload = {
        ...newUser,
        service_number: newUser.service_number?.trim() || null,
        department: newUser.department?.trim() || null,
        rank: newUser.rank?.trim() || null,
      }
      const res = await apiFetch('/users/', {
        method: 'POST',
        body: JSON.stringify(payload)
      })
      if (res && !res.detail) {
        setShowAddModal(false)
        setNewUser({ username: '', email: '', full_name: '', password: '', role: 'viewer', department: '', rank: '', service_number: '' })
        showToast('success', 'User created successfully')
        fetchUsers()
      } else {
        showToast('error', res?.detail || 'Failed to create user')
      }
    } catch (e) {
      console.error('Add user error:', e)
      showToast('error', 'Failed to add user')
    }
  }

  async function handleDeleteUser(userId, username) {
    if (!window.confirm(`Delete user "${username}"? This cannot be undone.`)) return
    try {
      const res = await apiFetch(`/users/${userId}`, { method: 'DELETE' })
      if (res && !res.detail) {
        showToast('success', `User "${username}" deleted`)
        fetchUsers()
      } else {
        showToast('error', res?.detail || 'Failed to delete user')
      }
    } catch (e) {
      showToast('error', 'Failed to delete user')
    }
  }

  async function handleUpdateUser() {
    if (!editUser) return
    try {
      const payload = {
        role: editUser.role,
        status: editUser.status,
        department: editUser.department?.trim() || null,
        rank: editUser.rank?.trim() || null,
        full_name: editUser.full_name,
        email: editUser.email,
      }
      const res = await apiFetch(`/users/${editUser.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      })
      if (res && !res.detail) {
        setEditUser(null)
        showToast('success', 'User updated successfully')
        fetchUsers()
      } else {
        showToast('error', res?.detail || 'Failed to update user')
      }
    } catch (e) {
      showToast('error', 'Failed to update user')
    }
  }

  const filteredUsers = users.filter(u =>
    u.username?.toLowerCase().includes(search.toLowerCase()) ||
    u.email?.toLowerCase().includes(search.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(search.toLowerCase())
  )

  const roleColors = {
    super_admin: { bg: 'rgba(239,68,68,0.12)', color: '#ef4444', label: 'Super Admin' },
    admin:       { bg: 'rgba(249,115,22,0.12)', color: '#f97316', label: 'Admin' },
    analyst:     { bg: 'rgba(74,139,255,0.12)', color: '#4a8bff', label: 'Analyst' },
    viewer:      { bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', label: 'Viewer' },
  }

  return (
    <div style={{ padding: '24px', position: 'relative' }}>
      {/* Toast notification */}
      {toast && (
        <div style={{
          position: 'fixed', top: '20px', right: '24px', zIndex: 9999,
          padding: '12px 20px', borderRadius: '10px', fontSize: '14px', fontWeight: 600,
          background: toast.type === 'success' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
          color: toast.type === 'success' ? '#22c55e' : '#ef4444',
          border: `1px solid ${toast.type === 'success' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
          backdropFilter: 'blur(8px)', animation: 'fadeIn 0.2s ease'
        }}>{toast.msg}</div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '28px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, margin: 0, color: '#fff' }}>User Management</h1>
          <p style={{ color: '#7a90b8', margin: '4px 0 0', fontSize: '13px' }}>
            {total} user{total !== 1 ? 's' : ''} in the system
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button onClick={fetchUsers} style={btnStyles.secondary} title="Refresh">
            <RefreshCw size={15} />
          </button>
          <button onClick={() => setShowAddModal(true)} style={btnStyles.primary}>
            <UserPlus size={16} />
            Add User
          </button>
        </div>
      </div>

      <div style={cardStyle}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#4a5e8a' }} />
            <input
              type="text"
              placeholder="Search by name, email or username…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '9px 12px 9px 38px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', color: '#fff', fontSize: '13px', outline: 'none' }}
            />
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                {['User', 'Role', 'Department', 'Status', 'Last Login', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '12px 18px', color: '#4a5e8a', fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="6" style={{ padding: '48px', textAlign: 'center' }}><Spinner size={28} /></td></tr>
              ) : filteredUsers.length === 0 ? (
                <tr><td colSpan="6" style={{ padding: '48px', textAlign: 'center', color: '#7a90b8' }}>No users found.</td></tr>
              ) : (
                filteredUsers.map((user) => {
                  const rc = roleColors[user.role] || roleColors.viewer
                  const isActive = user.status === 'active'
                  return (
                    <tr key={user.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', transition: 'background 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '14px 18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div style={{ width: '34px', height: '34px', borderRadius: '50%', background: 'linear-gradient(135deg,#1e6bff,#00c8e0)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '13px', color: '#fff', flexShrink: 0 }}>
                            {(user.full_name || user.username || 'U')[0].toUpperCase()}
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, color: '#fff', fontSize: '13px' }}>{user.full_name || user.username}</div>
                            <div style={{ fontSize: '11px', color: '#4a5e8a' }}>@{user.username} · {user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '14px 18px' }}>
                        <span style={{ padding: '3px 10px', borderRadius: '20px', background: rc.bg, color: rc.color, fontSize: '11px', fontWeight: 700 }}>
                          {rc.label}
                        </span>
                      </td>
                      <td style={{ padding: '14px 18px', color: '#7a90b8', fontSize: '12px' }}>
                        {user.department || <span style={{ color: '#334155' }}>—</span>}
                        {user.rank && <div style={{ fontSize: '11px', color: '#4a5e8a' }}>{user.rank}</div>}
                      </td>
                      <td style={{ padding: '14px 18px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                          {isActive
                            ? <><UserCheck size={13} color="#22c55e" /><span style={{ color: '#22c55e', fontSize: '12px', fontWeight: 600 }}>Active</span></>
                            : <><UserX size={13} color="#ef4444" /><span style={{ color: '#ef4444', fontSize: '12px', fontWeight: 600 }}>{user.status || 'Inactive'}</span></>
                          }
                        </div>
                      </td>
                      <td style={{ padding: '14px 18px', color: '#7a90b8', fontSize: '12px' }}>
                        {user.last_login ? new Date(user.last_login).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : 'Never'}
                      </td>
                      <td style={{ padding: '14px 18px' }}>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          {!user.is_superadmin && (
                            <>
                              <button onClick={() => setEditUser({ ...user })} style={btnStyles.iconBtn} title="Edit user">
                                <Edit2 size={14} />
                              </button>
                              <button onClick={() => handleDeleteUser(user.id, user.username)} style={{ ...btnStyles.iconBtn, color: '#ef4444' }} title="Delete user">
                                <Trash2 size={14} />
                              </button>
                            </>
                          )}
                          {user.is_superadmin && (
                            <span style={{ padding: '3px 8px', background: 'rgba(239,68,68,0.08)', color: '#ef4444', borderRadius: '6px', fontSize: '10px', fontWeight: 700 }}>
                              <Shield size={10} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                              SUPER
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Add User Modal ── */}
      {showAddModal && (
        <div style={modalOverlay}>
          <div style={modalBox}>
            <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#fff', margin: '0 0 20px' }}>Add New User</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[['Username *', 'username', 'text'], ['Email *', 'email', 'email'], ['Full Name *', 'full_name', 'text'], ['Password *', 'password', 'password'], ['Service Number', 'service_number', 'text'], ['Department', 'department', 'text'], ['Rank', 'rank', 'text']].map(([label, key, type]) => (
                <input key={key} type={type} placeholder={label} value={newUser[key] || ''}
                  onChange={e => setNewUser({ ...newUser, [key]: e.target.value })}
                  style={inputStyle} />
              ))}
              <select value={newUser.role} onChange={e => setNewUser({ ...newUser, role: e.target.value })} style={inputStyle}>
                <option value="viewer">Viewer</option>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
              <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
                <button onClick={handleAddUser} style={{ ...btnStyles.primary, flex: 1, justifyContent: 'center', padding: '11px' }}>Add User</button>
                <button onClick={() => setShowAddModal(false)} style={{ ...btnStyles.secondary, flex: 1, justifyContent: 'center', padding: '11px' }}>Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit User Modal ── */}
      {editUser && (
        <div style={modalOverlay}>
          <div style={modalBox}>
            <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#fff', margin: '0 0 20px' }}>Edit User — @{editUser.username}</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[['Full Name', 'full_name', 'text'], ['Email', 'email', 'email'], ['Department', 'department', 'text'], ['Rank', 'rank', 'text']].map(([label, key, type]) => (
                <input key={key} type={type} placeholder={label} value={editUser[key] || ''}
                  onChange={e => setEditUser({ ...editUser, [key]: e.target.value })}
                  style={inputStyle} />
              ))}
              <select value={editUser.role} onChange={e => setEditUser({ ...editUser, role: e.target.value })} style={inputStyle}>
                <option value="viewer">Viewer</option>
                <option value="analyst">Analyst</option>
                <option value="admin">Admin</option>
              </select>
              <select value={editUser.status} onChange={e => setEditUser({ ...editUser, status: e.target.value })} style={inputStyle}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="suspended">Suspended</option>
              </select>
              <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
                <button onClick={handleUpdateUser} style={{ ...btnStyles.primary, flex: 1, justifyContent: 'center', padding: '11px' }}>Save Changes</button>
                <button onClick={() => setEditUser(null)} style={{ ...btnStyles.secondary, flex: 1, justifyContent: 'center', padding: '11px' }}>Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Shared style objects ──
const cardStyle = {
  background: 'rgba(255,255,255,0.02)',
  border: '1px solid rgba(255,255,255,0.05)',
  borderRadius: '14px',
  overflow: 'hidden',
}
const modalOverlay = {
  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
  background: 'rgba(0,0,0,0.7)', display: 'flex',
  alignItems: 'center', justifyContent: 'center', zIndex: 1000,
}
const modalBox = {
  background: '#141927', border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '16px', padding: '28px', width: '90%', maxWidth: '460px',
}
const inputStyle = {
  padding: '10px 14px', background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px',
  color: '#fff', fontSize: '13px', outline: 'none', width: '100%',
}
const btnStyles = {
  primary: {
    display: 'flex', alignItems: 'center', gap: '7px',
    padding: '9px 16px', background: '#2463ff', color: '#fff',
    border: 'none', borderRadius: '9px', fontWeight: 600,
    cursor: 'pointer', fontSize: '13px',
  },
  secondary: {
    display: 'flex', alignItems: 'center', gap: '7px',
    padding: '9px 14px', background: 'rgba(255,255,255,0.06)', color: '#94a3b8',
    border: '1px solid rgba(255,255,255,0.08)', borderRadius: '9px', fontWeight: 500,
    cursor: 'pointer', fontSize: '13px',
  },
  iconBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: '30px', height: '30px', background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.06)', borderRadius: '7px',
    color: '#7a90b8', cursor: 'pointer', transition: 'all 0.15s',
  },
}
