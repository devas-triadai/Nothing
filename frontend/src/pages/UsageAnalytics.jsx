import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const StatCard = ({ label, value, unit, color }) => (
  <div style={{
    background: 'var(--surface)', borderRadius: '12px', padding: '24px',
    border: '1px solid var(--border)', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
  }}>
    <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px' }}>{label}</div>
    <div style={{ fontSize: '28px', fontWeight: 700, color: color || 'var(--text-primary)' }}>
      {value}<span style={{ fontSize: '14px', fontWeight: 400, marginLeft: '4px', color: 'var(--text-secondary)' }}>{unit}</span>
    </div>
  </div>
);

const UsageAnalytics = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('7d');

  useEffect(() => {
    const token = localStorage.getItem('agra_token');
    if (!token) { navigate('/login'); return; }
    fetchUsage();
  }, [period]);

  const fetchUsage = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch(`/api/usage?period=${period}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setStats(data.stats || null);
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Usage fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const statCards = stats ? [
    { label: 'Total API Calls', value: stats.totalCalls?.toLocaleString() || '0', color: '#1e6bff' },
    { label: 'Unique Users', value: stats.uniqueUsers?.toLocaleString() || '0', color: '#00c853' },
    { label: 'Avg Response Time', value: stats.avgResponseTime || '0', unit: 'ms', color: '#ff6d00' },
    { label: 'Error Rate', value: stats.errorRate || '0', unit: '%', color: '#d50000' },
  ] : [];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>Usage Analytics</h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>System usage metrics and performance data</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {['24h', '7d', '30d', '90d'].map(p => (
            <button key={p} onClick={() => setPeriod(p)} style={{
              padding: '7px 16px', borderRadius: '8px',
              border: period === p ? 'none' : '1px solid var(--border)',
              background: period === p ? '#1e6bff' : 'var(--surface)',
              color: period === p ? 'white' : 'var(--text-secondary)',
              fontSize: '12px', cursor: 'pointer', fontWeight: 500,
            }}>{p}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>Loading analytics...</div>
      ) : (
        <>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px', marginBottom: '28px',
          }}>
            {statCards.map(card => <StatCard key={card.label} {...card} />)}
          </div>

          {sessions.length > 0 && (
            <div style={{
              background: 'var(--surface)', borderRadius: '12px',
              border: '1px solid var(--border)', overflow: 'hidden',
              boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>Recent Sessions</h2>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--surface-hover)' }}>
                    {['User', 'Endpoint', 'Method', 'Status', 'Duration', 'Time'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                      onMouseLeave={e => e.currentTarget.style.background = ''}
                    >
                      <td style={{ padding: '10px 16px', fontSize: '13px' }}>{s.user}</td>
                      <td style={{ padding: '10px 16px', fontSize: '12px', fontFamily: 'monospace', color: 'var(--accent-blue-light)' }}>{s.endpoint}</td>
                      <td style={{ padding: '10px 16px' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
                          background: s.method === 'GET' ? 'rgba(0,200,83,0.15)' : s.method === 'POST' ? 'rgba(30,107,255,0.15)' : 'rgba(255,109,0,0.15)',
                          color: s.method === 'GET' ? '#00c853' : s.method === 'POST' ? '#1e6bff' : '#ff6d00',
                        }}>{s.method}</span>
                      </td>
                      <td style={{ padding: '10px 16px' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
                          background: s.status < 400 ? 'rgba(0,200,83,0.15)' : 'rgba(213,0,0,0.15)',
                          color: s.status < 400 ? '#00c853' : '#d50000',
                        }}>{s.status}</span>
                      </td>
                      <td style={{ padding: '10px 16px', fontSize: '12px', color: 'var(--text-secondary)' }}>{s.duration}ms</td>
                      <td style={{ padding: '10px 16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {s.timestamp ? new Date(s.timestamp).toLocaleString() : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {sessions.length === 0 && (
            <div style={{
              background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)',
              padding: '60px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '14px',
            }}>
              No usage data available for this period.
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default UsageAnalytics;
