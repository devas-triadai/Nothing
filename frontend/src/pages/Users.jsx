import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getToken, logout, getUser } from '../utils/auth';

const API = '/api';

async function apiFetch(path, opts = {}) {
  const token = getToken();
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {})
    }
  });
  if (res.status === 401) {
    logout();
    return null;
  }
  return res.json().catch(() => null);
}

export default function Users() {
  const navigate = useNavigate();
  const user = getUser();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/users/');
      setUsers(Array.isArray(data) ? data : (data?.items || []));
    } catch (err) {
      console.error('Users fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleUserStatus = async (userId, currentStatus) => {
    try {
      await apiFetch(`/users/${userId}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !currentStatus })
      });
      fetchUsers();
    } catch (err) {
      console.error('Status toggle error:', err);
    }
  };

  const filteredUsers = users.filter(u =>
    u.username?.toLowerCase().includes(search.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(search.toLowerCase()) ||
    u.email?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0b1020 0%, #111a2e 100%)',
      color: '#fff',
      fontFamily: 'Inter, system-ui, sans-serif',
      padding: '24px'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 32,
        paddingBottom: 20,
        borderBottom: '1px solid rgba(70,110,255,0.2)'
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>👥 User Management</h1>
          <p style={{ margin: '4px 0 0', color: '#7a90b8', fontSize: 13 }}>
            Manage system administrators and operators
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: '#9fb0d0', fontSize: 13 }}>{user?.username || 'Admin'}</span>
          <button onClick={() => logout()} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(255,80,80,0.3)',
            background: 'rgba(255,80,80,0.1)', color: '#ff9b9b', cursor: 'pointer', fontSize: 13, fontWeight: 600
          }}>Logout</button>
        </div>
      </div>

      {/* Nav */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 32, flexWrap: 'wrap' }}>
        {[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'Reports', path: '/reports' },
          { label: 'Agents', path: '/agents' },
          { label: 'Documents', path: '/documents' },
          { label: 'Audit Logs', path: '/audit-logs' },
          { label: 'Usage Analytics', path: '/usage-analytics' },
          { label: 'Settings', path: '/settings' }
        ].map(item => (
          <button key={item.path} onClick={() => navigate(item.path)} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(70,110,255,0.3)',
            background: item.path === '/users' ? 'rgba(36,99,255,0.2)' : 'rgba(36,99,255,0.1)',
            color: item.path === '/users' ? '#fff' : '#7ab4ff',
            cursor: 'pointer', fontSize: 13, fontWeight: 500
          }}>{item.label}</button>
        ))}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 24 }}>
        <input
          type="text"
          placeholder="Search users..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: 1, maxWidth: 400, background: '#1a2236', border: '1px solid #2d3b5a',
            color: '#fff', padding: '10px 16px', borderRadius: 10, outline: 'none'
          }}
        />
        <button onClick={() => setShowModal(true)} style={{
          padding: '10px 24px', borderRadius: 10, border: 'none',
          background: '#2463ff', color: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 600
        }}>+ Add User</button>
      </div>

      {/* Table */}
      <div style={{
        background: 'rgba(10,15,30,0.8)', border: '1px solid rgba(70,110,255,0.2)',
        borderRadius: 14, overflow: 'hidden'
      }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#7a90b8' }}>Loading users...</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: 'rgba(70,110,255,0.1)', borderBottom: '1px solid rgba(70,110,255,0.2)' }}>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>User</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Role</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Last Login</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Status</th>
                <th style={{ textAlign: 'right', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ padding: 40, textAlign: 'center', color: '#4a5e8a' }}>No users found.</td>
                </tr>
              ) : (
                filteredUsers.map((u) => (
                  <tr key={u.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ fontWeight: 600, color: '#fff' }}>{u.full_name || u.username}</div>
                      <div style={{ fontSize: 12, color: '#7a90b8' }}>{u.email || u.username}</div>
                    </td>
                    <td style={{ padding: '16px 20px', color: '#c8d8f0' }}>{u.role || 'Operator'}</td>
                    <td style={{ padding: '16px 20px', color: '#7a90b8' }}>
                      {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                    </td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{
                        padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                        background: u.is_active !== false ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        color: u.is_active !== false ? '#4ade80' : '#f87171'
                      }}>{u.is_active !== false ? 'Active' : 'Inactive'}</span>
                    </td>
                    <td style={{ padding: '16px 20px', textAlign: 'right' }}>
                      <button
                        onClick={() => toggleUserStatus(u.id, u.is_active)}
                        style={{
                          background: 'none', border: 'none', color: '#7ab4ff', cursor: 'pointer',
                          fontSize: 12, fontWeight: 600, marginRight: 12
                        }}
                      >
                        {u.is_active !== false ? 'Deactivate' : 'Activate'}
                      </button>
                      <button style={{
                        background: 'none', border: 'none', color: '#ff9b9b', cursor: 'pointer',
                        fontSize: 12, fontWeight: 600
                      }}>Delete</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
