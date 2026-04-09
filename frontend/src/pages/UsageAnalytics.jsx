import { useState, useEffect } from 'react';
import { apiFetch } from '../utils/api';
import Spinner from '../components/Spinner';
import { TrendingUp, Activity, Users, Zap, Clock, RefreshCw } from 'lucide-react';

const MetricCard = ({ icon: Icon, label, value, unit, color, change }) => (
  <div style={{
    background: 'var(--surface)',
    borderRadius: '12px',
    border: '1px solid var(--border)',
    padding: '20px',
    flex: '1 1 180px',
    minWidth: '180px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
      <div style={{ width: 36, height: 36, borderRadius: '8px', background: color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Icon size={18} color={color} />
      </div>
      {change !== undefined && (
        <span style={{ fontSize: '12px', fontWeight: 600, color: change >= 0 ? '#00c853' : '#d50000', background: change >= 0 ? 'rgba(0,200,83,0.1)' : 'rgba(213,0,0,0.1)', padding: '3px 8px', borderRadius: '20px' }}>
          {change >= 0 ? '+' : ''}{change}%
        </span>
      )}
    </div>
    <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>
      {value ?? '-'}
      {unit && <span style={{ fontSize: '14px', fontWeight: 400, color: 'var(--text-secondary)', marginLeft: '4px' }}>{unit}</span>}
    </div>
    <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px' }}>{label}</div>
  </div>
);

const PERIODS = ['24h', '7d', '30d', '90d'];

export default function UsageAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('7d');
  const [topAgents, setTopAgents] = useState([]);
  const [topUsers, setTopUsers] = useState([]);

  useEffect(() => {
    fetchAnalytics();
  }, [period]);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const result = await apiFetch(`/usage/analytics?period=${period}`);
      if (result) {
        setData(result);
        setTopAgents(result.top_agents || []);
        setTopUsers(result.top_users || []);
      }
    } catch (err) {
      console.error('Analytics fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
            <TrendingUp size={24} color="#1e6bff" />
            <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Usage Analytics</h1>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0, paddingLeft: '36px' }}>
            Platform usage metrics and trends
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ display: 'flex', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', overflow: 'hidden' }}>
            {PERIODS.map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                style={{
                  padding: '7px 14px',
                  border: 'none',
                  background: period === p ? '#1e6bff' : 'transparent',
                  color: period === p ? 'white' : 'var(--text-secondary)',
                  fontSize: '13px',
                  cursor: 'pointer',
                  fontWeight: period === p ? 600 : 400,
                }}
              >{p}</button>
            ))}
          </div>
          <button
            onClick={fetchAnalytics}
            style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '13px' }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px' }}>
          <Spinner size={32} />
        </div>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '24px' }}>
            <MetricCard icon={Activity} label="Total API Calls" value={data?.total_calls?.toLocaleString()} color="#1e6bff" change={data?.calls_change} />
            <MetricCard icon={Users} label="Active Users" value={data?.active_users} color="#00c853" change={data?.users_change} />
            <MetricCard icon={Zap} label="Avg Response Time" value={data?.avg_response_time} unit="ms" color="#f0b429" change={data?.response_change} />
            <MetricCard icon={Clock} label="Uptime" value={data?.uptime} unit="%" color="#00c853" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '20px' }}>
            <div style={{ background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Top Agents by Usage</h2>
              </div>
              {topAgents.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '13px' }}>No data available</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: 'var(--surface-hover)' }}>
                      {['Agent', 'Calls', 'Avg Time', 'Success Rate'].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {topAgents.map((agent, i) => (
                      <tr
                        key={agent.id || i}
                        style={{ borderBottom: '1px solid var(--border)' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}
                      >
                        <td style={{ padding: '10px 16px', fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>{agent.name || agent.agent_name}</td>
                        <td style={{ padding: '10px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>{agent.calls?.toLocaleString()}</td>
                        <td style={{ padding: '10px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>{agent.avg_time}ms</td>
                        <td style={{ padding: '10px 16px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'var(--border)', overflow: 'hidden' }}>
                              <div style={{ height: '100%', width: `${agent.success_rate || 0}%`, background: '#00c853', borderRadius: 3 }} />
                            </div>
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', minWidth: 32 }}>{agent.success_rate}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div style={{ background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Most Active Users</h2>
              </div>
              {topUsers.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '13px' }}>No data available</div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: 'var(--surface-hover)' }}>
                      {['User', 'Requests', 'Last Active'].map(h => (
                        <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {topUsers.map((user, i) => (
                      <tr
                        key={user.id || i}
                        style={{ borderBottom: '1px solid var(--border)' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-hover)'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}
                      >
                        <td style={{ padding: '10px 16px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#1e6bff22', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 700, color: '#1e6bff' }}>
                              {(user.name || user.username || '?')[0].toUpperCase()}
                            </div>
                            <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>{user.name || user.username}</span>
                          </div>
                        </td>
                        <td style={{ padding: '10px 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>{user.requests?.toLocaleString()}</td>
                        <td style={{ padding: '10px 16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {user.last_active ? new Date(user.last_active).toLocaleDateString() : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
