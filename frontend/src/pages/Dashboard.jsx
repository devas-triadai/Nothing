import { useState, useEffect } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import { Users, CheckCircle, BarChart3, FileText } from 'lucide-react'

export default function Dashboard() {
  const [stats, setStats] = useState({
    totalUsers: 0,
    activeUsers: 0,
    totalQueries: 0,
    indexedDocs: 0
  })
  const [recentActivity, setRecentActivity] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDashboardData()
  }, [])

  async function fetchDashboardData() {
    setLoading(true)
    try {
      const [statsData, activityData] = await Promise.all([
        apiFetch('/dashboard/stats'),
        apiFetch('/dashboard/activity?limit=8')
      ])

      if (statsData) {
        setStats({
          totalUsers: statsData.users?.total ?? 0,
          activeUsers: statsData.users?.active ?? 0,
          totalQueries: statsData.usage?.total_queries ?? 0,
          indexedDocs: statsData.documents?.indexed ?? 0
        })
      }

      if (activityData) {
        const items = Array.isArray(activityData) ? activityData : (activityData.items || activityData.logs || [])
        setRecentActivity(items.slice(0, 8))
      }
    } catch (e) {
      console.error('Dashboard fetch error:', e)
    } finally {
      setLoading(false)
    }
  }

  const statCards = [
    { label: 'Total Users', value: stats.totalUsers, icon: Users, color: '#2463ff' },
    { label: 'Active Users', value: stats.activeUsers, icon: CheckCircle, color: '#22c55e' },
    { label: 'Total Queries', value: stats.totalQueries, icon: BarChart3, color: '#f59e0b' },
    { label: 'Indexed Docs', value: stats.indexedDocs, icon: FileText, color: '#ef4444' }
  ]

  if (loading) {
    return <Spinner size={36} />
  }

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: 'var(--text-heading)' }}>Dashboard Overview</h1>
        <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: '14px' }}>System status and recent activity</p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '20px',
        marginBottom: '32px'
      }}>
        {statCards.map((card, i) => (
          <div key={i} style={{
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
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
              <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-heading)' }}>{card.value}</div>
              <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>{card.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{
        background: 'var(--card-bg)',
        border: '1px solid var(--card-border)',
        borderRadius: '16px',
        padding: '24px'
      }}>
        <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '0 0 20px', color: 'var(--text-heading)' }}>Recent Activity</h2>
        {recentActivity.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>No recent activity to display.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {recentActivity.map((log, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 16px',
                borderRadius: '10px',
                background: 'var(--card-hover)',
                border: '1px solid var(--card-border)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2463ff' }}></div>
                  <span style={{ color: 'var(--text-primary)', fontSize: '14px' }}>{log.action || log.event || 'System Event'}</span>
                </div>
                <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
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
