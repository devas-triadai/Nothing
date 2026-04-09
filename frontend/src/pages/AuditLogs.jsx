import { useState, useEffect } from 'react';
import { getToken, logout } from '../utils/auth';
import { Shield, Search, Filter } from 'lucide-react';

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

const ACTION_COLORS = {
  login: { bg: 'rgba(0,200,83,0.15)', color: '#00c853' },
  logout: { bg: 'rgba(136,153,187,0.15)', color: '#8899bb' },
  create: { bg: 'rgba(30,107,255,0.15)', color: '#1e6bff' },
  update: { bg: 'rgba(255,109,0,0.15)', color: '#ff6d00' },
  delete: { bg: 'rgba(213,0,0,0.15)', color: '#d50000' },
  access: { bg: 'rgba(240,180,41,0.15)', color: '#f0b429' },
};

const ACTION_FILTERS = ['all', 'login', 'logout', 'create', 'update', 'delete', 'access'];

const AuditLogs = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [actionFilter, setActionFilter] = useState('all');

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/audit/');
      if (data) setLogs(data.logs || []);
    } catch (err) {
      console.error('Audit logs fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredLogs = logs.filter(log => {
    const matchesSearch = !search ||
      log.user?.toLowerCase().includes(search.toLowerCase()) ||
      log.description?.toLowerCase().includes(search.toLowerCase()) ||
      log.ip_address?.toLowerCase().includes(search.toLowerCase());
    const matchesAction = actionFilter === 'all' || log.action === actionFilter;
    return matchesSearch && matchesAction;
  });

  const getActionStyle = (action) => {
    const c = ACTION_COLORS[action?.toLowerCase()] || { bg: 'rgba(136,153,187,0.15)', color: '#8899bb' };
    return {
      display: 'inline-block',
      padding: '3px 10px',
      borderRadius: '12px',
      fontSize: '11px',
      fontWeight: 600,
      background: c.bg,
      color: c.color,
      textTransform: 'capitalize',
    };
  };

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
          <Shield size={24} color="#1e6bff" />
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Audit Logs</h1>
        </div>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0, paddingLeft: '36px' }}>
          Complete record of all system actions and events
        </p>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
          <input
            type="text"
            placeholder="Search user, action, IP..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: '8px 14px 8px 30px',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text-primary)',
              fontSize: '13px',
              outline: 'none',
              width: '260px',
            }}
          />
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {ACTION_FILTERS.map(a => (
            <button
              key={a}
              onClick={() => setActionFilter(a)}
              style={{
                padding: '6px 14px',
                borderRadius: '20px',
                border: actionFilter === a ? 'none' : '1px solid var(--border)',
                background: actionFilter === a ? '#1e6bff' : 'var(--surface)',
                color: actionFilter === a ? 'white' : 'var(--text-secondary)',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: 500,
                textTransform: 'capitalize',
              }}
            >{a}</button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', fontSize: '13px', color: 'var(--text-secondary)' }}>
          {filteredLogs.length} records
        </div>
      </div>

      <div style={{ background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
            Loading audit logs...
          </div>
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
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>
                    No audit logs found
                  </td>
                </tr>
              ) : filteredLogs.map((log, i) => (
                <tr
                  key={log.id || i}
                  style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '11px 16px', fontSize: '12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                  </td>
                  <td style={{ padding: '11px 16px', fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                    {log.user || log.username || 'System'}
                  </td>
                  <td style={{ padding: '11px 16px' }}>
                    <span style={getActionStyle(log.action)}>{log.action || 'unknown'}</span>
                  </td>
                  <td style={{ padding: '11px 16px', fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.description || log.details || '-'}
                  </td>
                  <td style={{ padding: '11px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                    {log.ip_address || log.ip || '-'}
                  </td>
                  <td style={{ padding: '11px 16px' }}>
                    <span style={{
                      display: 'inline-block',
                      padding: '3px 10px',
                      borderRadius: '12px',
                      fontSize: '11px',
                      fontWeight: 600,
                      background: log.result === 'success' || log.status === 'success' ? 'rgba(0,200,83,0.15)' : 'rgba(213,0,0,0.15)',
                      color: log.result === 'success' || log.status === 'success' ? '#00c853' : '#d50000',
                    }}>
                      {log.result || log.status || 'unknown'}
                    </span>
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
