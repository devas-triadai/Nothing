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

const StatCard = ({ label, value, unit, color }) => (
  <div style={{
    background: 'rgba(10,15,30,0.8)', borderRadius: '14px', padding: '24px',
    border: `1px solid ${color || 'rgba(70,110,255,0.2)'}`,
    boxShadow: '0 4px 20px rgba(0,0,0,0.2)'
  }}>
    <div style={{ fontSize: '13px', color: '#7a90b8', marginBottom: '8px' }}>{label}</div>
    <div style={{ fontSize: '28px', fontWeight: 800, color: color || '#fff' }}>
      {value}<span style={{ fontSize: '14px', fontWeight: 400, marginLeft: '4px', color: '#7a90b8' }}>{unit}</span>
    </div>
  </div>
);

export default function UsageAnalytics() {
  const navigate = useNavigate();
  const user = getUser();
  const [stats, setStats] = useState({
    apiCalls: '1.2M',
    avgLatency: '142',
    activeSessions: '842',
    storageUsed: '45.2'
  });
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('7d');

  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }
    // Simulate loading
    setTimeout(() => setLoading(false), 800);
  }, []);

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
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>📈 Usage Analytics</h1>
          <p style={{ margin: '4px 0 0', color: '#7a90b8', fontSize: 13 }}>
            Real-time system performance and resource monitoring
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
          { label: 'Users', path: '/users' },
          { label: 'Reports', path: '/reports' },
          { label: 'Agents', path: '/agents' },
          { label: 'Documents', path: '/documents' },
          { label: 'Audit Logs', path: '/audit-logs' },
          { label: 'Settings', path: '/settings' }
        ].map(item => (
          <button key={item.path} onClick={() => navigate(item.path)} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(70,110,255,0.3)',
            background: 'rgba(36,99,255,0.1)', color: '#7ab4ff', cursor: 'pointer', fontSize: 13, fontWeight: 500
          }}>{item.label}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#7a90b8' }}>Analyzing system data...</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20, marginBottom: 32 }}>
            <StatCard label="Total API Requests" value={stats.apiCalls} color="#2463ff" />
            <StatCard label="Avg. Latency" value={stats.avgLatency} unit="ms" color="#22c55e" />
            <StatCard label="Active Sessions" value={stats.activeSessions} color="#f59e0b" />
            <StatCard label="Storage Usage" value={stats.storageUsed} unit="GB" color="#ef4444" />
          </div>

          <div style={{
            background: 'rgba(10,15,30,0.8)', border: '1px solid rgba(70,110,255,0.2)',
            borderRadius: 14, padding: 24, marginBottom: 32
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>System Load Trend</h2>
              <select value={period} onChange={(e) => setPeriod(e.target.value)} style={{
                background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '6px 12px', borderRadius: 6
              }}>
                <option value="24h">Last 24 Hours</option>
                <option value="7d">Last 7 Days</option>
                <option value="30d">Last 30 Days</option>
              </select>
            </div>
            <div style={{
              height: 200, display: 'flex', alignItems: 'flex-end', gap: 10, padding: '0 10px'
            }}>
              {[40, 65, 45, 80, 55, 90, 70, 85, 60, 75, 50, 95].map((h, i) => (
                <div key={i} style={{
                  flex: 1, height: `${h}%`, background: 'linear-gradient(to top, #2463ff, #7ab4ff)',
                  borderRadius: '4px 4px 0 0', opacity: 0.8
                }}></div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12, color: '#4a5e8a', fontSize: 12 }}>
              <span>00:00</span>
              <span>06:00</span>
              <span>12:00</span>
              <span>18:00</span>
              <span>23:59</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
            <div style={{ background: 'rgba(10,15,30,0.8)', border: '1px solid rgba(70,110,255,0.2)', borderRadius: 14, padding: 24 }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>Top API Endpoints</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {[
                  { path: '/api/v1/search', count: '452k', p: 85 },
                  { path: '/api/v1/auth/login', count: '128k', p: 40 },
                  { path: '/api/v1/agents/chat', count: '94k', p: 30 },
                  { path: '/api/v1/users/profile', count: '62k', p: 20 }
                ].map((item, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
                      <span style={{ color: '#c8d8f0', fontFamily: 'monospace' }}>{item.path}</span>
                      <span style={{ color: '#7a90b8' }}>{item.count}</span>
                    </div>
                    <div style={{ height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
                      <div style={{ height: '100%', width: `${item.p}%`, background: '#2463ff', borderRadius: 2 }}></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
