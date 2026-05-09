import { useState, useEffect } from 'react';
import { apiFetch } from '../utils/api';
import Spinner from '../components/Spinner';
import { BarChart2, Download, RefreshCw, TrendingUp, Users, FileText, Activity, Bot, Calendar, Clock } from 'lucide-react';

const StatCard = ({ icon: Icon, label, value, change, color }) => (
  <div style={{
    background: 'var(--surface)',
    borderRadius: '12px',
    border: '1px solid var(--border)',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    flex: '1 1 180px',
    minWidth: '180px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ width: 36, height: 36, borderRadius: '8px', background: color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Icon size={18} color={color} />
      </div>
      <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</span>
    </div>
    <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)' }}>{value ?? '-'}</div>
    {change !== undefined && (
      <div style={{ fontSize: '12px', color: change >= 0 ? '#00c853' : '#d50000' }}>
        {change >= 0 ? '+' : ''}{change}% from last period
      </div>
    )}
  </div>
);

/* ── Table wrapper for consistent styling ── */
const TableCard = ({ title, subtitle, children }) => (
  <div style={{ background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
    <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>{title}</h2>
      {subtitle && <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{subtitle}</span>}
    </div>
    {children}
  </div>
);

export default function Reports() {
  const [stats, setStats] = useState(null);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  // Tab-specific data
  const [usageData, setUsageData] = useState([]);
  const [usageLoading, setUsageLoading] = useState(false);
  const [agentsData, setAgentsData] = useState([]);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [topUsers, setTopUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  // Fetch tab-specific data when tab changes
  useEffect(() => {
    if (activeTab === 'usage' && usageData.length === 0) fetchUsageData();
    if (activeTab === 'agents' && agentsData.length === 0) fetchAgentsData();
    if (activeTab === 'users' && topUsers.length === 0) fetchTopUsers();
  }, [activeTab]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsData, reportsData] = await Promise.all([
        apiFetch('/reports/summary'),
        apiFetch('/reports/'),
      ]);
      if (statsData) setStats(statsData);
      if (reportsData) setReports(Array.isArray(reportsData.reports) ? reportsData.reports : []);
    } catch (err) {
      console.error('Reports fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchUsageData = async () => {
    setUsageLoading(true);
    try {
      const data = await apiFetch('/reports/usage-over-time?days=30');
      if (data?.data) setUsageData(data.data);
    } catch (err) {
      console.error('Usage data fetch error:', err);
    } finally {
      setUsageLoading(false);
    }
  };

  const fetchAgentsData = async () => {
    setAgentsLoading(true);
    try {
      const data = await apiFetch('/agents/');
      setAgentsData(Array.isArray(data) ? data : (data?.items || []));
    } catch (err) {
      console.error('Agents fetch error:', err);
    } finally {
      setAgentsLoading(false);
    }
  };

  const fetchTopUsers = async () => {
    setUsersLoading(true);
    try {
      const data = await apiFetch('/reports/top-users?limit=10');
      setTopUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Top users fetch error:', err);
    } finally {
      setUsersLoading(false);
    }
  };

  const handleExport = async () => {
    try {
      const data = await apiFetch(`/reports/export?report_type=usage&days=30`);
      if (!data) return;
      // Convert JSON to CSV
      const rows = data.data || [];
      if (rows.length === 0) { alert('No data to export.'); return; }
      const headers = Object.keys(rows[0]);
      const csvContent = [
        headers.join(','),
        ...rows.map(row => headers.map(h => JSON.stringify(row[h] ?? '')).join(','))
      ].join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `agra_${data.report_type}_report_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Export error:', e);
      alert('Failed to export report.');
    }
  };

  const handleDownloadReport = async (report) => {
    const typeMap = { usage: 'usage', users: 'users', documents: 'audit' };
    const reportType = typeMap[report.type] || 'usage';
    try {
      const data = await apiFetch(`/reports/export?report_type=${reportType}&days=30`);
      if (!data) return;
      const rows = data.data || [];
      if (rows.length === 0) { alert('No data available for this report.'); return; }
      const headers = Object.keys(rows[0]);
      const csvContent = [
        headers.join(','),
        ...rows.map(row => headers.map(h => JSON.stringify(row[h] ?? '')).join(','))
      ].join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `agra_${report.name?.replace(/\s+/g, '_') || 'report'}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Download report error:', e);
      alert('Failed to download report.');
    }
  };

  const tabs = ['overview', 'usage', 'agents', 'users'];

  /* ═══════════════════════════════════════════
     TAB CONTENT RENDERERS
  ═══════════════════════════════════════════ */

  const renderOverviewTab = () => (
    <div>
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '24px' }}>
        <StatCard icon={Users} label="Total Users" value={stats?.total_users ?? stats?.users} change={stats?.user_change} color="#1e6bff" />
        <StatCard icon={Activity} label="Active Sessions" value={stats?.active_sessions ?? stats?.sessions} change={stats?.session_change} color="#00c853" />
        <StatCard icon={FileText} label="Documents" value={stats?.total_documents ?? stats?.documents} change={stats?.doc_change} color="#f0b429" />
        <StatCard icon={TrendingUp} label="API Calls" value={stats?.api_calls ?? stats?.requests} change={stats?.api_change} color="#ff6d00" />
      </div>

      <TableCard title="Recent Reports" subtitle={`${reports.length} reports`}>
        {reports.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>
            No reports available
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--surface-hover)' }}>
                {['Report Name', 'Type', 'Generated', 'Status', 'Actions'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reports.map((report, i) => (
                <tr
                  key={report.id || i}
                  style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '12px 16px', fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                    {report.name || report.title || 'Untitled'}
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {report.type || '-'}
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {report.created_at ? new Date(report.created_at).toLocaleDateString() : '-'}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      display: 'inline-block', padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
                      background: report.status === 'completed' ? 'rgba(0,200,83,0.15)' : 'rgba(240,180,41,0.15)',
                      color: report.status === 'completed' ? '#00c853' : '#f0b429',
                    }}>{report.status || 'pending'}</span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <button onClick={() => handleDownloadReport(report)} style={{ background: 'none', border: 'none', color: '#1e6bff', fontSize: '12px', cursor: 'pointer', fontWeight: 500 }}>Download</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </TableCard>
    </div>
  );

  const renderUsageTab = () => (
    <div>
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '24px' }}>
        <StatCard icon={Activity} label="Total API Calls" value={stats?.api_calls} color="#1e6bff" change={stats?.api_change} />
        <StatCard icon={Clock} label="Queries (30d)" value={stats?.queries_last_30_days} color="#00c853" />
        <StatCard icon={Users} label="Active Users" value={stats?.active_users} color="#f0b429" />
      </div>

      <TableCard title="Daily Usage (Last 30 Days)" subtitle={`${usageData.length} days`}>
        {usageLoading ? (
          <div style={{ textAlign: 'center', padding: '40px' }}><Spinner size={28} /></div>
        ) : usageData.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>
            No usage data available for this period
          </div>
        ) : (
          <>
            {/* Simple bar visualization */}
            <div style={{ padding: '20px', display: 'flex', alignItems: 'flex-end', gap: '3px', height: '160px', borderBottom: '1px solid var(--border)' }}>
              {usageData.map((d, i) => {
                const maxCount = Math.max(...usageData.map(x => x.count), 1);
                const heightPct = (d.count / maxCount) * 100;
                return (
                  <div
                    key={i}
                    title={`${d.date}: ${d.count} calls`}
                    style={{
                      flex: 1,
                      height: `${Math.max(heightPct, 2)}%`,
                      background: 'linear-gradient(180deg, #1e6bff, #3d8bff)',
                      borderRadius: '3px 3px 0 0',
                      minWidth: '4px',
                      cursor: 'pointer',
                      transition: 'opacity 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.opacity = '0.7'}
                    onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                  />
                );
              })}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--surface-hover)' }}>
                  {['Date', 'API Calls'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {usageData.slice().reverse().slice(0, 15).map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}
                  >
                    <td style={{ padding: '10px 16px', fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Calendar size={14} color="var(--text-muted)" />
                        {row.date}
                      </div>
                    </td>
                    <td style={{ padding: '10px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                      <span style={{ fontWeight: 600, color: '#1e6bff' }}>{row.count}</span> calls
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </TableCard>
    </div>
  );

  const renderAgentsTab = () => (
    <div>
      <TableCard title="Agent Configurations" subtitle={`${agentsData.length} agents`}>
        {agentsLoading ? (
          <div style={{ textAlign: 'center', padding: '40px' }}><Spinner size={28} /></div>
        ) : agentsData.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>
            No agents configured yet
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--surface-hover)' }}>
                {['Agent Name', 'Model', 'Status', 'Description'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agentsData.map((agent, i) => (
                <tr key={agent.id || i} style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ width: 32, height: 32, borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(30,107,255,0.08)', flexShrink: 0 }}>
                        <Bot size={16} color="#1e6bff" />
                      </div>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '13px' }}>{agent.name}</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 10px', borderRadius: '6px', fontSize: '12px', fontWeight: 500, background: 'rgba(30,107,255,0.08)', color: '#3d8bff' }}>
                      {agent.value || agent.model || 'Gemma (Local)'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: '4px',
                      padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
                      background: agent.is_active !== false ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                      color: agent.is_active !== false ? '#22c55e' : '#ef4444',
                    }}>
                      <Activity size={10} />
                      {agent.is_active !== false ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {agent.description || 'No description'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </TableCard>
    </div>
  );

  const renderUsersTab = () => (
    <div>
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '24px' }}>
        <StatCard icon={Users} label="Total Users" value={stats?.total_users} color="#1e6bff" change={stats?.user_change} />
        <StatCard icon={Activity} label="Active Users" value={stats?.active_users} color="#00c853" />
      </div>

      <TableCard title="Top Users by Activity" subtitle={`${topUsers.length} users`}>
        {usersLoading ? (
          <div style={{ textAlign: 'center', padding: '40px' }}><Spinner size={28} /></div>
        ) : topUsers.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)', fontSize: '14px' }}>
            No user activity data available
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--surface-hover)' }}>
                {['#', 'User', 'Email', 'Queries'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topUsers.map((user, i) => (
                <tr key={user.user_id || i} style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '12px 16px', fontSize: '13px', color: 'var(--text-muted)', fontWeight: 700, width: '40px' }}>
                    {i + 1}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'linear-gradient(135deg, #1e6bff, #00c8e0)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '12px', color: '#fff', flexShrink: 0 }}>
                        {(user.username || '?')[0].toUpperCase()}
                      </div>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '13px' }}>{user.username}</span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {user.email || '-'}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ fontWeight: 700, color: '#1e6bff', fontSize: '14px' }}>{user.query_count}</span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '4px' }}>queries</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </TableCard>
    </div>
  );

  /* ═══════════════════════════════════════════
     MAIN RENDER
  ═══════════════════════════════════════════ */

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
            <BarChart2 size={24} color="#1e6bff" />
            <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Reports</h1>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0, paddingLeft: '36px' }}>
            Analytics and performance insights
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => { fetchData(); if (activeTab === 'usage') fetchUsageData(); if (activeTab === 'agents') fetchAgentsData(); if (activeTab === 'users') fetchTopUsers(); }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-primary)', fontSize: '13px', cursor: 'pointer', fontWeight: 500 }}
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            onClick={handleExport}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#1e6bff', color: 'white', fontSize: '13px', cursor: 'pointer', fontWeight: 500 }}
          >
            <Download size={14} /> Export
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', borderBottom: '1px solid var(--border)', paddingBottom: '0' }}>
        {tabs.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              color: activeTab === tab ? '#1e6bff' : 'var(--text-secondary)',
              fontSize: '13px',
              cursor: 'pointer',
              fontWeight: activeTab === tab ? 600 : 400,
              borderBottom: activeTab === tab ? '2px solid #1e6bff' : '2px solid transparent',
              textTransform: 'capitalize',
              marginBottom: '-1px',
            }}
          >{tab}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px' }}>
          <Spinner size={32} />
        </div>
      ) : (
        <>
          {activeTab === 'overview' && renderOverviewTab()}
          {activeTab === 'usage' && renderUsageTab()}
          {activeTab === 'agents' && renderAgentsTab()}
          {activeTab === 'users' && renderUsersTab()}
        </>
      )}
    </div>
  );
}
