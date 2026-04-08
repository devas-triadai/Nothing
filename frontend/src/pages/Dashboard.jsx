import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getToken, getUser, logout } from '../utils/auth'

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

export default function Dashboard() {
  const navigate = useNavigate()
  const user = getUser()
  const [stats, setStats] = useState({
    totalUsers: 0,
    activeUsers: 0,
    totalReports: 0,
    pendingActions: 0
  })
  const [recentActivity, setRecentActivity] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      navigate('/login')
      return
    }
    fetchDashboardData()
  }, [])

  async function fetchDashboardData() {
    setLoading(true)
    try {
      const [usersData, reportsData, logsData] = await Promise.all([
        apiFetch('/users/'),
        apiFetch('/reports/'),
        apiFetch('/audit-logs/')
      ])
      const users = Array.isArray(usersData) ? usersData : (usersData?.items || [])
      const reports = Array.isArray(reportsData) ? reportsData : (reportsData?.items || [])
      const logs = Array.isArray(logsData) ? logsData : (logsData?.items || [])
      setStats({
        totalUsers: users.length,
        activeUsers: users.filter(u => u.is_active !== false).length,
        totalReports: reports.length,
        pendingActions: reports.filter(r => r.status === 'pending').length
      })
      setRecentActivity(logs.slice(0, 8))
    } catch (e) {
      console.error('Dashboard fetch error:', e)
    } finally {
      setLoading(false)
    }
  }

  const statCards = [
    { label: 'Total Users', value: stats.totalUsers, icon: '👥', color: '#2463ff' },
    { label: 'Active Users', value: stats.activeUsers, icon: '✅', color: '#22c55e' },
    { label: 'Total Reports', value: stats.totalReports, icon: '📊', color: '#f59e0b' },
    { label: 'Pending Actions', value: stats.pendingActions, icon: '⏳', color: '#ef4444' }
  ]

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
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>🛡️ AGRA Dashboard</h1>
          <p style={{ margin: '4px 0 0', color: '#7a90b8', fontSize: 13 }}>
            Indian Coast Guard — Super Admin
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: '#9fb0d0', fontSize: 13 }}>
            {user?.username || user?.full_name || 'Admin'}
          </span>
          <button
            onClick={() => logout()}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: '1px solid rgba(255,80,80,0.3)',
              background: 'rgba(255,80,80,0.1)',
              color: '#ff9b9b',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 600
            }}
          >
            Logout
          </button>
        </div>
      </div>

      {/* Nav */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 32, flexWrap: 'wrap' }}>
        {[
          { label: 'Users', path: '/users' },
          { label: 'Reports', path: '/reports' },
          { label: 'Agents', path: '/agents' },
          { label: 'Documents', path: '/documents' },
          { label: 'Audit Logs', path: '/audit-logs' },
          { label: 'Usage Analytics', path: '/usage-analytics' },
          { label: 'Settings', path: '/settings' }
        ].map(item => (
          <button
            key={item.path}
            onClick={() => navigate(item.path)}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: '1px solid rgba(70,110,255,0.3)',
              background: 'rgba(36,99,255,0.1)',
              color: '#7ab4ff',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 500
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Stats */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#7a90b8' }}>Loading...</div>
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 16,
            marginBottom: 32
          }}>
            {statCards.map(card => (
              <div key={card.label} style={{
                background: 'rgba(10,15,30,0.8)',
                border: `1px solid ${card.color}33`,
                borderRadius: 14,
                padding: '20px 24px'
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>{card.icon}</div>
                <div style={{ fontSize: 32, fontWeight: 800, color: card.color }}>{card.value}</div>
                <div style={{ fontSize: 13, color: '#7a90b8', marginTop: 4 }}>{card.label}</div>
              </div>
            ))}
          </div>

          {/* Recent Activity */}
          <div style={{
            background: 'rgba(10,15,30,0.8)',
            border: '1px solid rgba(70,110,255,0.2)',
            borderRadius: 14,
            padding: 24
          }}>
            <h2 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Recent Activity</h2>
            {recentActivity.length === 0 ? (
              <p style={{ color: '#4a5e8a', fontSize: 14 }}>No recent activity.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {recentActivity.map((log, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    borderRadius: 8,
                    background: 'rgba(255,255,255,0.03)',
                    fontSize: 13
                  }}>
                    <span style={{ color: '#c8d8f0' }}>{log.action || log.event || 'Activity'}</span>
                    <span style={{ color: '#4a5e8a' }}>
                      {log.created_at ? new Date(log.created_at).toLocaleString() : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
