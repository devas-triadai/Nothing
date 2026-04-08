import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState({
    totalUsers: 0,
    activeUsers: 0,
    totalReports: 0,
    pendingActions: 0,
  });
  const [recentActivity, setRecentActivity] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('agra_token');
    if (!token) {
      navigate('/login');
      return;
    }
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const token = localStorage.getItem('agra_token');
      const response = await fetch('/api/dashboard/stats', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setStats(data.stats || stats);
        setRecentActivity(data.recentActivity || []);
      }
    } catch (err) {
      console.error('Dashboard fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    { label: 'Total Users', value: stats.totalUsers, icon: '👥', color: '#1e6bff' },
    { label: 'Active Users', value: stats.activeUsers, icon: '✅', color: '#00c853' },
    { label: 'Total Reports', value: stats.totalReports, icon: '📊', color: '#ff6d00' },
    { label: 'Pending Actions', value: stats.pendingActions, icon: '⏳', color: '#d50000' },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px', color: 'var(--text-primary)' }}>
        Dashboard Overview
      </h1>
      <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '32px' }}>
        Welcome back, Super Admin
      </p>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
          Loading dashboard data...
        </div>
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '20px',
            marginBottom: '32px',
          }}>
            {statCards.map((card) => (
              <div key={card.label} style={{
                background: 'var(--surface)',
                borderRadius: '12px',
                padding: '24px',
                border: '1px solid var(--border)',
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
              }}>
                <div style={{ fontSize: '32px', marginBottom: '12px' }}>{card.icon}</div>
                <div style={{ fontSize: '28px', fontWeight: 700, color: card.color, marginBottom: '4px' }}>
                  {card.value.toLocaleString()}
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                  {card.label}
                </div>
              </div>
            ))}
          </div>

          <div style={{
            background: 'var(--surface)',
            borderRadius: '12px',
            border: '1px solid var(--border)',
            padding: '24px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
          }}>
            <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-primary)' }}>
              Recent Activity
            </h2>
            {recentActivity.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>No recent activity found.</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['User', 'Action', 'Time', 'Status'].map((h) => (
                      <th key={h} style={{ textAlign: 'left', padding: '8px 12px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentActivity.map((item, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '10px 12px', fontSize: '13px' }}>{item.user}</td>
                      <td style={{ padding: '10px 12px', fontSize: '13px' }}>{item.action}</td>
                      <td style={{ padding: '10px 12px', fontSize: '13px', color: 'var(--text-secondary)' }}>{item.time}</td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '20px',
                          fontSize: '11px',
                          fontWeight: 600,
                          background: item.status === 'success' ? 'rgba(0,200,83,0.15)' : 'rgba(213,0,0,0.15)',
                          color: item.status === 'success' ? '#00c853' : '#d50000',
                        }}>
                          {item.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
