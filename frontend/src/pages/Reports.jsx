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

export default function Reports() {
  const navigate = useNavigate();
  const user = getUser();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }
    fetchReports();
  }, []);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/reports/');
      setReports(Array.isArray(data) ? data : (data?.items || []));
    } catch (err) {
      console.error('Reports fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format) => {
    alert(`Exporting as ${format}... (Feature coming soon)`);
  };

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
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>📊 Reports</h1>
          <p style={{ margin: '4px 0 0', color: '#7a90b8', fontSize: 13 }}>
            System Analytics & Data Export
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
          { label: 'Agents', path: '/agents' },
          { label: 'Documents', path: '/documents' },
          { label: 'Audit Logs', path: '/audit-logs' },
          { label: 'Usage Analytics', path: '/usage-analytics' },
          { label: 'Settings', path: '/settings' }
        ].map(item => (
          <button key={item.path} onClick={() => navigate(item.path)} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(70,110,255,0.3)',
            background: 'rgba(36,99,255,0.1)', color: '#7ab4ff', cursor: 'pointer', fontSize: 13, fontWeight: 500
          }}>{item.label}</button>
        ))}
      </div>

      {/* Controls */}
      <div style={{
        display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap',
        background: 'rgba(10,15,30,0.5)', padding: 16, borderRadius: 12, border: '1px solid rgba(70,110,255,0.1)'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 11, color: '#7a90b8' }}>Filter Type</label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{
            background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '6px 12px', borderRadius: 6
          }}>
            <option value="all">All Reports</option>
            <option value="usage">Usage Stats</option>
            <option value="errors">Error Logs</option>
            <option value="security">Security Alerts</option>
          </select>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 11, color: '#7a90b8' }}>From</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={{
              background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '6px 12px', borderRadius: 6
            }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <label style={{ fontSize: 11, color: '#7a90b8' }}>To</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={{
              background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '6px 12px', borderRadius: 6
            }} />
          </div>
        </div>
        <div style={{ flex: 1 }}></div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <button onClick={() => handleExport('csv')} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid #22c55e',
            background: 'rgba(34,197,94,0.1)', color: '#4ade80', cursor: 'pointer', fontSize: 13, fontWeight: 600
          }}>Export CSV</button>
          <button onClick={() => handleExport('pdf')} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid #ef4444',
            background: 'rgba(239,68,68,0.1)', color: '#f87171', cursor: 'pointer', fontSize: 13, fontWeight: 600
          }}>Export PDF</button>
        </div>
      </div>

      {/* Content */}
      <div style={{
        background: 'rgba(10,15,30,0.8)', border: '1px solid rgba(70,110,255,0.2)',
        borderRadius: 14, overflow: 'hidden'
      }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#7a90b8' }}>Loading reports...</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: 'rgba(70,110,255,0.1)', borderBottom: '1px solid rgba(70,110,255,0.2)' }}>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>ID</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Title</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Category</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Date</th>
                <th style={{ textAlign: 'left', padding: '16px 20px', color: '#7a90b8', fontWeight: 600 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {reports.length === 0 ? (
                <tr>
                  <td colSpan="5" style={{ padding: 40, textAlign: 'center', color: '#4a5e8a' }}>No reports found for the selected period.</td>
                </tr>
              ) : (
                reports.map((report) => (
                  <tr key={report.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '16px 20px', color: '#c8d8f0' }}>#{report.id}</td>
                    <td style={{ padding: '16px 20px', fontWeight: 500 }}>{report.title}</td>
                    <td style={{ padding: '16px 20px', color: '#7a90b8' }}>{report.category}</td>
                    <td style={{ padding: '16px 20px', color: '#7a90b8' }}>{new Date(report.created_at).toLocaleDateString()}</td>
                    <td style={{ padding: '16px 20px' }}>
                      <span style={{
                        padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                        background: report.status === 'completed' ? 'rgba(34,197,94,0.1)' : 'rgba(245,158,11,0.1)',
                        color: report.status === 'completed' ? '#4ade80' : '#fbbf24'
                      }}>{report.status}</span>
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
