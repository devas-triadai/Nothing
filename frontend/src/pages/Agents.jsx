import { useState, useEffect } from 'react'
import { getToken, logout } from '../utils/auth'
import { Bot, Settings2, Activity, Cpu, Zap, Plus, Search, Trash2, Edit2 } from 'lucide-react'

const API = '/api'

async function apiFetch(path, opts = {}) {
  const token = getToken()
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {})
    }
  })
  if (res.status === 401) {
    logout()
    return null
  }
  return res.json().catch(() => null)
}

export default function Agents() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchAgents()
  }, [])

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

  const filteredAgents = agents.filter(a => 
    a.name?.toLowerCase().includes(search.toLowerCase()) || 
    a.model?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: '32px' 
      }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#fff' }}>Agent Configuration</h1>
          <p style={{ color: '#7a90b8', margin: '4px 0 0', fontSize: '14px' }}>Manage AI models and system prompts</p>
        </div>
        <button style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 18px',
          background: '#2463ff',
          color: '#fff',
          border: 'none',
          borderRadius: '10px',
          fontWeight: 600,
          cursor: 'pointer',
          fontSize: '14px'
        }}>
          <Plus size={18} />
          New Agent
        </button>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '20px'
      }}>
        {loading ? (
          <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: '40px', color: '#7a90b8' }}>Loading agents...</div>
        ) : filteredAgents.length === 0 ? (
          <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: '40px', color: '#7a90b8' }}>No agents configured yet.</div>
        ) : (
          filteredAgents.map((agent, i) => (
            <div key={i} style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              borderRadius: '16px',
              padding: '24px',
              position: 'relative'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
                <div style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '10px',
                  background: 'rgba(36, 99, 255, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#7ab4ff'
                }}>
                  <Bot size={24} />
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button style={{ background: 'none', border: 'none', color: '#4a5e8a', cursor: 'pointer' }}><Edit2 size={16} /></button>
                  <button style={{ background: 'none', border: 'none', color: '#4a5e8a', cursor: 'pointer' }}><Trash2 size={16} /></button>
                </div>
              </div>

              <h3 style={{ margin: '0 0 8px', color: '#fff', fontSize: '18px' }}>{agent.name}</h3>
              <p style={{ margin: '0 0 20px', color: '#7a90b8', fontSize: '14px', lineHeight: '1.5', height: '42px', overflow: 'hidden' }}>
                {agent.description || 'No description provided.'}
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Cpu size={14} color=\"#4a5e8a\" />
                  <span style={{ fontSize: '13px', color: '#7a90b8' }}>Model: <span style={{ color: '#c8d8f0' }}>{agent.model || 'GPT-4'}</span></span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Zap size={14} color=\"#4a5e8a\" />
                  <span style={{ fontSize: '13px', color: '#7a90b8' }}>Version: <span style={{ color: '#c8d8f0' }}>v{agent.version || '1.0'}</span></span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={14} color=\"#22c55e\" />
                  <span style={{ fontSize: '13px', color: '#22c55e', fontWeight: 600 }}>System Active</span>
                </div>
              </div>

              <button style={{
                marginTop: '24px',
                width: '100%',
                padding: '10px',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                borderRadius: '8px',
                color: '#7ab4ff',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer'
              }}>
                Configure Agent
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
