import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const AuditLogs = () => {
  const navigate = useNavigate();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [actionFilter, setActionFilter] = useState('all');

  useEffect(() => {
    const token = localStorage.getItem('agra_token');
    if (!token) { navigate('/login'); return; }
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch('/api/audit', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
      }
    } catch (err) {
      console.error('Audit logs fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const actionColors = {
    login: { bg: 'rgba(0,200,83,0.15)', color: '#00c853' },
    logout: { bg: 'rgba(136,153,187,0.15)', color: '#8899bb' },
    create: { bg: 'rgba(30,107,255,0.15)', color: '#1e6bff' },
    update: { bg: 'rgba(255,109,0,0.15)', color: '#ff6d00' },
    delete: { bg: 'rgba(213,0,0,0.15)', color: '#d50000' },
    access: { bg: 'rgba(240,180,41,0.15)', color: '#f0b429' },
  };

  const actions = ['all', 'login', 'logout', 'create', 'update', 'delete', 'access'];

  const filteredLogs = logs.filter(log => {
    const matchesSearch = !search ||
      log.user?.toLowerCase().includes(search.toLowerCase()) ||
      log.description?.toLowerCase().includes(search.toLowerCase());
    const matchesAction = actionFilter === 'all' || log.action === actionFilter;
    return matchesSearch && matchesAction;
  });

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>Audit Logs</h1>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>Complete record of all system actions</p>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search by user or action..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            padding: '8px 14px', borderRadius: '8px', border: '1px solid var(--border)',
            background: 'var(--surface)', color: 'var(--text-primary)', fontSize: '13px',
            outline: 'none', width: '260px',
          }}
        />
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {actions.map(a => (
            <button key={a} onClick={() => setActionFilter(a)} style={{
              padding: '6px 14px', borderRadius: '20px',
              border: actionFilter === a ? 'none' : '1px solid var(--border)',
              background: actionFilter === a ? '#1e6bff' : 'var(--surface)',
              color: actionFilter === a ? 'white' : 'var(--text-secondary)',
              fontSize: '12px', cursor: 'pointer', fontWeight: 500, textTransform: 'capitalize',
            }}>{a}</button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', fontSize: '13px', color: 'var(--text-secondary)' }}>
          {filteredLogs.length} records
        </div>
      </div>

      <div style={{
        background: 'var(--surface)', borderRadius: '12px',
        border: '1px solid var(--border)', overflow: 'hidden',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>Loading audit logs...</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--surface-hover)' }}>
                {['Timestamp', 'User', 'Action', 'Description', 'IP Address', 'Result'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredLogs.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>No audit logs found</td></tr>
              ) : filteredLogs.map((log, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '11px 16px', fontSize: '12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                  </td>
                  <td style={{ padding: '11px 16px', fontSize: '13px', fontWeight: 500 }}>{log.user || '-'}</td>
                  <td style={{ padding: '11px 16px' }}>
                    <span style={{
                      padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                      background: actionColors[log.action]?.bg || 'rgba(255,255,255,0.08)',
                      color: actionColors[log.action]?.color || 'var(--text-secondary)',
                      textTransform: 'capitalize',
                    }}>{log.action || 'unknown'}</span>
                  </td>
                  <td style={{ padding: '11px 16px', fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.description || '-'}
                  </td>
                  <td style={{ padding: '11px 16px', fontSize: '12px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                    {log.ip_address || '-'}
                  </td>
                  <td style={{ padding: '11px 16px' }}>
                    <span style={{
                      padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                      background: log.result === 'success' ? 'rgba(0,200,83,0.15)' : 'rgba(213,0,0,0.15)',
                      color: log.result === 'success' ? '#00c853' : '#d50000',
                    }}>{log.result || 'unknown'}</span>
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

export default AuditLogs;
