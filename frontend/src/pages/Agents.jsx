import { useState, useEffect, useMemo } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import {
  Bot, Activity, Cpu, Zap, Plus, Search, Trash2, Edit2,
  ExternalLink, ChevronUp, ChevronDown, Filter,
} from 'lucide-react'

const STATUS_OPTIONS = ['All', 'Active', 'Inactive'];

export default function Agents() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')

  useEffect(() => { fetchAgents() }, [])

  async function fetchAgents() {
    setLoading(true)
    try {
      const data = await apiFetch('/agents/')
      setAgents(Array.isArray(data) ? data : (data?.items || []))
    } catch (e) {
      console.error('Fetch agents error:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const SortIcon = ({ col }) => {
    if (sortKey !== col) return <ChevronUp size={12} style={{ opacity: 0.2 }} />
    return sortDir === 'asc'
      ? <ChevronUp size={12} style={{ opacity: 0.8 }} />
      : <ChevronDown size={12} style={{ opacity: 0.8 }} />
  }

  const filtered = useMemo(() => {
    let list = agents.filter(a => {
      const q = search.toLowerCase()
      const matchSearch = !q ||
        a.name?.toLowerCase().includes(q) ||
        a.model?.toLowerCase().includes(q) ||
        a.description?.toLowerCase().includes(q)
      const matchStatus = statusFilter === 'All' || (statusFilter === 'Active')
      return matchSearch && matchStatus
    })

    list.sort((a, b) => {
      const av = (a[sortKey] || '').toString().toLowerCase()
      const bv = (b[sortKey] || '').toString().toLowerCase()
      const cmp = av.localeCompare(bv)
      return sortDir === 'asc' ? cmp : -cmp
    })

    return list
  }, [agents, search, statusFilter, sortKey, sortDir])

  const openAgentUI = () => {
    const token = localStorage.getItem('agra_token')
    let targetUrl = 'http://localhost:7860'
    if (window.location.hostname.includes('runpod.net')) {
      // Auto-detect Agent UI port from current origin
      const agentPort = '7860'
      targetUrl = window.location.origin.replace(/:\d+/, ':' + agentPort)
      if (!window.location.origin.includes(':')) {
        // RunPod proxy URL format: <pod-id>-<port>.proxy.runpod.net
        targetUrl = window.location.origin.replace(/\d{4}(?=\.proxy)/, agentPort)
      }
    }
    window.open(`${targetUrl}/?token=${token}`, '_blank')
  }

  const columns = [
    { key: 'name', label: 'Name', width: '20%' },
    { key: 'model', label: 'Model', width: '15%' },
    { key: 'version', label: 'Version', width: '10%' },
    { key: 'status', label: 'Status', width: '10%' },
    { key: 'description', label: 'Description', width: '30%' },
    { key: '_actions', label: 'Actions', width: '15%' },
  ]

  return (
    <div style={{ padding: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={s.heading}>Agent Configuration</h1>
          <p style={s.subheading}>Manage AI models and system prompts</p>
        </div>
        <button style={s.primaryBtn}>
          <Plus size={18} />
          New Agent
        </button>
      </div>

      {/* Toolbar: Search + Filter */}
      <div style={s.toolbar}>
        <div style={s.searchBox}>
          <Search size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by name, model, or description…"
            style={s.searchInput}
          />
        </div>
        <div style={s.filterBox}>
          <Filter size={14} style={{ color: 'var(--text-muted)' }} />
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={s.filterSelect}>
            {STATUS_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
      </div>

      {/* Table */}
      <div style={s.tableWrap}>
        {loading ? (
          <div style={s.center}><Spinner size={28} /></div>
        ) : filtered.length === 0 ? (
          <div style={s.center}>
            <Bot size={32} style={{ opacity: 0.15 }} />
            <span style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '8px' }}>
              {agents.length === 0 ? 'No agents configured yet.' : 'No agents match your filters.'}
            </span>
          </div>
        ) : (
          <table style={s.table}>
            <thead>
              <tr>
                {columns.map(col => (
                  <th
                    key={col.key}
                    onClick={col.key !== '_actions' ? () => handleSort(col.key) : undefined}
                    style={{
                      ...s.th,
                      width: col.width,
                      cursor: col.key !== '_actions' ? 'pointer' : 'default',
                      userSelect: 'none',
                    }}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {col.label}
                      {col.key !== '_actions' && <SortIcon col={col.key} />}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((agent, i) => (
                <tr key={i} style={s.tr}>
                  <td style={s.td}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={s.agentIcon}><Bot size={16} /></div>
                      <span style={{ fontWeight: 600, color: 'var(--text-heading)' }}>{agent.name}</span>
                    </div>
                  </td>
                  <td style={s.td}>
                    <span style={s.modelBadge}>
                      <Cpu size={11} />
                      {agent.model || 'GPT-4'}
                    </span>
                  </td>
                  <td style={{ ...s.td, fontFamily: 'monospace', fontSize: '13px' }}>
                    v{agent.version || '1.0'}
                  </td>
                  <td style={s.td}>
                    <span style={s.statusBadge}>
                      <Activity size={10} />
                      Active
                    </span>
                  </td>
                  <td style={{ ...s.td, color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {agent.description || 'No description provided.'}
                  </td>
                  <td style={s.td}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button onClick={openAgentUI} style={s.actionBtn} title="Open Agent UI">
                        <ExternalLink size={14} />
                      </button>
                      <button style={s.actionBtn} title="Edit"><Edit2 size={14} /></button>
                      <button style={{ ...s.actionBtn, color: 'var(--accent-red)' }} title="Delete"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const s = {
  heading: { fontSize: '24px', fontWeight: 700, margin: 0, color: 'var(--text-heading)' },
  subheading: { color: 'var(--text-secondary)', margin: '4px 0 0', fontSize: '14px' },
  primaryBtn: {
    display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 18px',
    background: 'var(--accent-blue)', color: '#fff', border: 'none', borderRadius: '10px',
    fontWeight: 600, cursor: 'pointer', fontSize: '14px',
  },
  toolbar: {
    display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap',
  },
  searchBox: {
    display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '240px',
    padding: '9px 14px', background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: '10px',
  },
  searchInput: {
    flex: 1, border: 'none', background: 'transparent', color: 'var(--text-primary)',
    fontSize: '13px', outline: 'none',
  },
  filterBox: {
    display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 14px',
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '10px',
  },
  filterSelect: {
    border: 'none', background: 'transparent', color: 'var(--text-primary)',
    fontSize: '13px', outline: 'none', cursor: 'pointer',
  },
  tableWrap: {
    background: 'var(--card-bg)', border: '1px solid var(--card-border)',
    borderRadius: '14px', overflow: 'hidden',
  },
  center: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: '48px', gap: '8px',
  },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: {
    textAlign: 'left', padding: '12px 16px', fontSize: '12px', fontWeight: 600,
    color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px',
    borderBottom: '1px solid var(--border)', background: 'var(--surface)',
  },
  tr: {
    borderBottom: '1px solid var(--border)', transition: 'background 0.15s',
  },
  td: { padding: '14px 16px', fontSize: '14px', color: 'var(--text-primary)' },
  agentIcon: {
    width: 32, height: 32, borderRadius: '8px', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
    background: 'rgba(30, 107, 255, 0.08)', color: 'var(--accent-blue-light)',
    flexShrink: 0,
  },
  modelBadge: {
    display: 'inline-flex', alignItems: 'center', gap: '4px',
    padding: '3px 10px', borderRadius: '6px', fontSize: '12px', fontWeight: 500,
    background: 'rgba(30, 107, 255, 0.08)', color: 'var(--accent-blue-light)',
  },
  statusBadge: {
    display: 'inline-flex', alignItems: 'center', gap: '4px',
    padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
    background: 'rgba(34, 197, 94, 0.1)', color: '#22c55e',
  },
  actionBtn: {
    background: 'none', border: '1px solid var(--border)', borderRadius: '6px',
    padding: '5px 8px', cursor: 'pointer', color: 'var(--text-secondary)',
    display: 'flex', alignItems: 'center', transition: 'all 0.15s',
  },
}
