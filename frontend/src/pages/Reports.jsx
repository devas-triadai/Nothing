import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Reports = () => {
  const navigate = useNavigate();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('agra_token');
    if (!token) { navigate('/login'); return; }
    fetchReports();
  }, []);

  const fetchReports = async () => {
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch('/api/reports', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setReports(data.reports || []);
      }
    } catch (err) {
      console.error('Reports fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format) => {
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch(`/api/reports/export?format=${format}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `agra-report.${format}`;
        a.click();
      }
    } catch (err) {
      console.error('Export error:', err);
    }
  };

  const filteredReports = reports.filter(r => filter === 'all' || r.type === filter);

  const typeColors = {
    audit: { bg: 'rgba(30,107,255,0.15)', color: '#1e6bff' },
    security: { bg: 'rgba(213,0,0,0.15)', color: '#d50000' },
    activity: { bg: 'rgba(0,200,83,0.15)', color: '#00c853' },
    system: { bg: 'rgba(255,109,0,0.15)', color: '#ff6d00' },
  };

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>Reports</h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>View and export system reports</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => handleExport('csv')}
            style={{
              padding: '9px 18px', borderRadius: '8px', border: '1px solid var(--border)',
              background: 'var(--surface)', color: 'var(--text-primary)', fontSize: '13px',
              cursor: 'pointer', fontWeight: 500,
            }}
          >
            Export CSV
          </button>
          <button
            onClick={() => handleExport('pdf')}
            style={{
              padding: '9px 18px', borderRadius: '8px', border: 'none',
              background: 'linear-gradient(135deg, #1e6bff, #3d8bff)', color: 'white',
              fontSize: '13px', cursor: 'pointer', fontWeight: 500,
            }}
          >
            Export PDF
          </button>
        </div>
      </div>

      <div style={{
        display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center',
      }}>
        {['all', 'audit', 'security', 'activity', 'system'].map(type => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            style={{
              padding: '6px 16px', borderRadius: '20px', border: '1px solid var(--border)',
              background: filter === type ? '#1e6bff' : 'var(--surface)',
              color: filter === type ? 'white' : 'var(--text-secondary)',
              fontSize: '12px', cursor: 'pointer', fontWeight: 500, textTransform: 'capitalize',
            }}
          >
            {type}
          </button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-primary)', fontSize: '12px' }}
          />
          <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>to</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-primary)', fontSize: '12px' }}
          />
        </div>
      </div>

      <div style={{
        background: 'var(--surface)', borderRadius: '12px',
        border: '1px solid var(--border)', boxShadow: '0 2px 8px rgba(0,0,0,0.15)', overflow: 'hidden',
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>Loading reports...</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--surface-hover)' }}>
                {['Report ID', 'Type', 'Generated By', 'Date', 'Status', 'Actions'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredReports.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>No reports found</td></tr>
              ) : filteredReports.map(report => (
                <tr key={report.id} style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '12px 16px', fontSize: '13px', fontFamily: 'monospace' }}>#{report.id}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                      background: typeColors[report.type]?.bg || 'rgba(255,255,255,0.08)',
                      color: typeColors[report.type]?.color || 'var(--text-secondary)',
                    }}>{report.type}</span>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>{report.generatedBy}</td>
                  <td style={{ padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {report.date ? new Date(report.date).toLocaleString() : 'N/A'}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                      background: report.status === 'completed' ? 'rgba(0,200,83,0.15)' : 'rgba(255,109,0,0.15)',
                      color: report.status === 'completed' ? '#00c853' : '#ff6d00',
                    }}>{report.status}</span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <button style={{
                      padding: '5px 12px', borderRadius: '6px', border: '1px solid var(--border)',
                      background: 'transparent', color: 'var(--text-primary)', fontSize: '12px', cursor: 'pointer',
                    }}>View</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default Reports;
