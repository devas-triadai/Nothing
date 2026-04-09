import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getToken, logout } from '../utils/auth'
import { Users, CheckCircle, BarChart3, Clock } from 'lucide-react'

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
    { label: 'Total Users', value: stats.totalUsers, icon: Users, color: '#2463ff' },
    { label: 'Active Users', value: stats.activeUsers, icon: CheckCircle, color: '#22c55e' },
    { label: 'Total Reports', value: stats.totalReports, icon: BarChart3, color: '#f59e0b' },
    { label: 'Pending Actions', value: stats.pendingActions, icon: Clock, color: '#ef4444' }
  ]

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#7a90b8' }}>
        Loading dashboard data...
      </div>
    )
  }

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#fff' }}>Dashboard Overview</h1>
        <p style={{ color: '#7a90b8', margin: '4px 0 0', fontSize: '14px' }}>System status and recent activity</p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '20px',
        marginBottom: '32px'
      }}>
        {statCards.map((card, i) => (
          <div key={i} style={{
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            borderRadius: '16px',
            padding: '24px',
            display: 'flex',
            alignItems: 'center',
            gap: '20px'
          }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              background: `${card.color}15`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: card.color
            }}>
              <card.icon size={24} />
            </div>
            <div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: '#fff' }}>{card.value}</div>
              <div style={{ fontSize: '14px', color: '#7a90b8' }}>{card.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        borderRadius: '16px',
        padding: '24px'
      }}>
        <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 20px', color: '#fff' }}>Recent Activity</h2>
        {recentActivity.length === 0 ? (
          <p style={{ color: '#4a5e8a', fontSize: '14px' }}>No recent activity to display.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {recentActivity.map((log, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 16px',
                borderRadius: '10px',
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.03)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2463ff' }}></div>
                  <span style={{ color: '#c8d8f0', fontSize: '14px' }}>{log.action || log.event || 'System Event'}</span>
                </div>
                <span style={{ color: '#4a5e8a', fontSize: '12px' }}>
                  {log.created_at ? new Date(log.created_at).toLocaleString() : ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
