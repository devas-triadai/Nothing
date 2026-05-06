import { useState, useEffect, useMemo } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import {
  Bot, Activity, Cpu, Zap, Plus, Search, Trash2, Edit2,
  ExternalLink, ChevronUp, ChevronDown, Filter, X, Save,
} from 'lucide-react'

const STATUS_OPTIONS = ['All', 'Active', 'Inactive'];

const MODEL_OPTIONS = [
  'Gemma 4 (Primary)',
  'Gemma 2B (Fast)',
  'Llama 3 70B (Heavy)',
  'Llama 3 8B (Light)',
  'Mistral 7B',
  'Custom Local Model',
];

const EMPTY_FORM = { name: '', value: '', description: '' };

export default function Agents() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [houseRules, setHouseRules] = useState('')
  const [savingRules, setSavingRules] = useState(false)

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState('create') // 'create' | 'edit'
  const [formData, setFormData] = useState({ ...EMPTY_FORM })
  const [editingId, setEditingId] = useState(null)
  const [saving, setSaving] = useState(false)

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

  async function fetchHouseRules() {
    try {
      const data = await apiFetch('/agents/house-rules')
      setHouseRules(data.house_rules || '')
    } catch (e) {
      console.error('Fetch house rules error:', e)
    }
  }

  useEffect(() => { 
    fetchAgents()
    fetchHouseRules()
  }, [])

  async function saveHouseRules() {
    setSavingRules(true)
    try {
      await apiFetch('/agents/house-rules', {
        method: 'PUT',
        body: JSON.stringify({ house_rules: houseRules })
      })
      alert('System prompt updated successfully.')
    } catch (e) {
      console.error('Save rules error:', e)
      alert('Failed to save system prompt.')
    } finally {
      setSavingRules(false)
    }
  }

  // ── CRUD Handlers ──
  function openCreateModal() {
    setModalMode('create')
    setFormData({ ...EMPTY_FORM })
    setEditingId(null)
    setShowModal(true)
  }

  function openEditModal(agent) {
    setModalMode('edit')
    setFormData({
      name: agent.name || '',
      value: agent.value || agent.model || '',
      description: agent.description || '',
    })
    setEditingId(agent.id)
    setShowModal(true)
  }

  async function handleSaveAgent() {
    if (!formData.name.trim()) { alert('Agent name is required.'); return; }
    setSaving(true)
    try {
      if (modalMode === 'create') {
        await apiFetch('/agents/', {
          method: 'POST',
          body: JSON.stringify(formData)
        })
      } else {
        await apiFetch(`/agents/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify({
            value: formData.value,
            description: formData.description,
          })
        })
      }
      setShowModal(false)
      fetchAgents()
    } catch (e) {
      console.error('Save agent error:', e)
      alert('Failed to save agent configuration.')
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteAgent(agent) {
    if (!window.confirm(`Delete agent "${agent.name}"? This action cannot be undone.`)) return;
    try {
      await apiFetch(`/agents/${agent.id}`, { method: 'DELETE' })
      setAgents(prev => prev.filter(a => a.id !== agent.id))
    } catch (e) {
      console.error('Delete agent error:', e)
      alert('Failed to delete agent.')
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
    const token = localStorage.getItem('agra_token') || '';
    let targetUrl = `${window.location.protocol}//${window.location.hostname}:7860`
    if (window.location.hostname.includes('runpod.net')) {
      const agentPort = '7860'
      if (window.location.origin.match(/:\d+/)) {
        targetUrl = window.location.origin.replace(/:\d+/, ':' + agentPort)
      } else {
        targetUrl = window.location.origin.replace(/\d{4}(?=\.proxy)/, agentPort)
      }
    }
    window.open(`${targetUrl}/?token=${token}`, '_blank')
  }

  const columns = [
    { key: 'name', label: 'Name', width: '20%' },
    { key: 'value', label: 'Model', width: '15%' },
    { key: 'is_active', label: 'Status', width: '10%' },
    { key: 'description', label: 'Description', width: '35%' },
    { key: '_actions', label: 'Actions', width: '20%' },
  ]

  return (
    <div style={{ padding: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={s.heading}>Agent Configuration</h1>
          <p style={s.subheading}>Manage AI models and system prompts</p>
        </div>
        <button onClick={openCreateModal} style={s.primaryBtn}>
          <Plus size={18} />
          New Agent
        </button>
      </div>

      {/* Global System Prompt */}
      <div style={{ ...s.tableWrap, padding: '20px', marginBottom: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-heading)', margin: 0 }}>Global System Prompt (House Rules)</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '4px 0 0' }}>These instructions will be prepended to every RAG query across all agents.</p>
          </div>
          <button 
            onClick={saveHouseRules} 
            disabled={savingRules}
            style={{ ...s.primaryBtn, background: 'var(--accent-green)', padding: '8px 16px', fontSize: '13px' }}
          >
            {savingRules ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
        <textarea
          value={houseRules}
          onChange={(e) => setHouseRules(e.target.value)}
          placeholder="Enter global constraints or instructions... e.g. 'Always respond in formal defense terminology'"
          style={{
            width: '100%',
            height: '120px',
            padding: '12px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            color: 'var(--text-primary)',
            fontSize: '14px',
            fontFamily: 'monospace',
            outline: 'none',
            resize: 'vertical'
          }}
        />
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
              {agents.length === 0 ? 'No agents configured yet. Click "New Agent" to create one.' : 'No agents match your filters.'}
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
                <tr key={agent.id || i} style={s.tr}>
                  <td style={s.td}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={s.agentIcon}><Bot size={16} /></div>
                      <span style={{ fontWeight: 600, color: 'var(--text-heading)' }}>{agent.name}</span>
                    </div>
                  </td>
                  <td style={s.td}>
                    <span style={s.modelBadge}>
                      <Cpu size={11} />
                      {agent.value || agent.model || 'Gemma (Local)'}
                    </span>
                  </td>
                  <td style={s.td}>
                    <span style={agent.is_active !== false ? s.statusBadge : s.statusInactive}>
                      <Activity size={10} />
                      {agent.is_active !== false ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ ...s.td, color: 'var(--text-secondary)', fontSize: '13px', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {agent.description || 'No description provided.'}
                  </td>
                  <td style={s.td}>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button onClick={openAgentUI} style={s.actionBtn} title="Open Agent UI">
                        <ExternalLink size={14} />
                      </button>
                      <button onClick={() => openEditModal(agent)} style={s.actionBtn} title="Edit">
                        <Edit2 size={14} />
                      </button>
                      <button onClick={() => handleDeleteAgent(agent)} style={{ ...s.actionBtn, color: 'var(--accent-red)' }} title="Delete">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ═══ Create / Edit Modal ═══ */}
      {showModal && (
        <div style={s.overlay}>
          <div style={s.modal}>
            <div style={s.modalHeader}>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-heading)', margin: 0 }}>
                {modalMode === 'create' ? 'Create New Agent' : 'Edit Agent'}
              </h2>
              <button onClick={() => setShowModal(false)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            <div style={s.modalBody}>
              {/* Name */}
              <div style={s.formGroup}>
                <label style={s.label}>Agent Name *</label>
                <input
                  value={formData.name}
                  onChange={e => setFormData(p => ({ ...p, name: e.target.value }))}
                  placeholder="e.g. RAG Primary, Document Classifier"
                  disabled={modalMode === 'edit'}
                  style={{
                    ...s.input,
                    opacity: modalMode === 'edit' ? 0.6 : 1,
                    cursor: modalMode === 'edit' ? 'not-allowed' : 'text',
                  }}
                />
              </div>

              {/* Model */}
              <div style={s.formGroup}>
                <label style={s.label}>Model</label>
                <select
                  value={formData.value}
                  onChange={e => setFormData(p => ({ ...p, value: e.target.value }))}
                  style={s.input}
                >
                  <option value="">Select a model...</option>
                  {MODEL_OPTIONS.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>

              {/* Description */}
              <div style={s.formGroup}>
                <label style={s.label}>Description</label>
                <textarea
                  value={formData.description}
                  onChange={e => setFormData(p => ({ ...p, description: e.target.value }))}
                  placeholder="What does this agent do? e.g. Handles complex RAG queries..."
                  rows={3}
                  style={{ ...s.input, resize: 'vertical' }}
                />
              </div>
            </div>

            <div style={s.modalFooter}>
              <button
                onClick={handleSaveAgent}
                disabled={saving}
                style={{ ...s.primaryBtn, flex: 1, justifyContent: 'center', opacity: saving ? 0.6 : 1 }}
              >
                <Save size={15} />
                {saving ? 'Saving...' : (modalMode === 'create' ? 'Create Agent' : 'Save Changes')}
              </button>
              <button
                onClick={() => setShowModal(false)}
                style={{ ...s.cancelBtn, flex: 1 }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
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
  cancelBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', padding: '10px 18px',
    background: 'var(--surface)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: '10px',
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
  statusInactive: {
    display: 'inline-flex', alignItems: 'center', gap: '4px',
    padding: '3px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600,
    background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444',
  },
  actionBtn: {
    background: 'none', border: '1px solid var(--border)', borderRadius: '6px',
    padding: '5px 8px', cursor: 'pointer', color: 'var(--text-secondary)',
    display: 'flex', alignItems: 'center', transition: 'all 0.15s',
  },

  // Modal styles
  overlay: {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0, 0, 0, 0.6)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  },
  modal: {
    background: 'var(--card-bg, var(--surface))', border: '1px solid var(--border)',
    borderRadius: '16px', width: '90%', maxWidth: '520px',
    boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
  },
  modalHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '20px 24px', borderBottom: '1px solid var(--border)',
  },
  modalBody: {
    padding: '24px', display: 'flex', flexDirection: 'column', gap: '18px',
  },
  modalFooter: {
    display: 'flex', gap: '12px', padding: '16px 24px',
    borderTop: '1px solid var(--border)',
  },
  formGroup: {
    display: 'flex', flexDirection: 'column', gap: '6px',
  },
  label: {
    fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)',
  },
  input: {
    padding: '10px 14px', background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: '8px', color: 'var(--text-primary)', fontSize: '14px', outline: 'none',
    fontFamily: 'inherit',
  },
}
