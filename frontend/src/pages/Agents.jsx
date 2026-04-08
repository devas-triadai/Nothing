import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Agents = () => {
  const navigate = useNavigate();
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);
  const [form, setForm] = useState({ name: '', description: '', model: '', systemPrompt: '', isActive: true });

  useEffect(() => {
    const token = localStorage.getItem('agra_token');
    if (!token) { navigate('/login'); return; }
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch('/api/agents', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents || []);
      }
    } catch (err) {
      console.error('Agents fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      const token = localStorage.getItem('agra_token');
      const method = editingAgent ? 'PUT' : 'POST';
      const url = editingAgent ? `/api/agents/${editingAgent.id}` : '/api/agents';
      const res = await fetch(url, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        const data = await res.json();
        if (editingAgent) {
          setAgents(agents.map(a => a.id === editingAgent.id ? data.agent : a));
        } else {
          setAgents([...agents, data.agent]);
        }
        setShowForm(false);
        setEditingAgent(null);
        setForm({ name: '', description: '', model: '', systemPrompt: '', isActive: true });
      }
    } catch (err) {
      console.error('Save agent error:', err);
    }
  };

  const handleDelete = async (agentId) => {
    if (!confirm('Delete this agent?')) return;
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch(`/api/agents/${agentId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setAgents(agents.filter(a => a.id !== agentId));
    } catch (err) {
      console.error('Delete agent error:', err);
    }
  };

  const handleEdit = (agent) => {
    setEditingAgent(agent);
    setForm({ name: agent.name, description: agent.description, model: agent.model, systemPrompt: agent.systemPrompt, isActive: agent.isActive });
    setShowForm(true);
  };

  const inputStyle = {
    width: '100%', padding: '9px 12px', borderRadius: '8px',
    border: '1px solid var(--border)', background: 'var(--bg)',
    color: 'var(--text-primary)', fontSize: '13px', outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>Agent Configuration</h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>Configure and manage AI agents</p>
        </div>
        <button
          onClick={() => { setEditingAgent(null); setForm({ name: '', description: '', model: '', systemPrompt: '', isActive: true }); setShowForm(true); }}
          style={{
            padding: '10px 20px', borderRadius: '8px', border: 'none',
            background: 'linear-gradient(135deg, #1e6bff, #3d8bff)',
            color: 'white', fontSize: '13px', cursor: 'pointer', fontWeight: 600,
          }}
        >
          + New Agent
        </button>
      </div>

      {showForm && (
        <div style={{
          background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)',
          padding: '24px', marginBottom: '24px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        }}>
          <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '20px' }}>
            {editingAgent ? 'Edit Agent' : 'Create New Agent'}
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            <div>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Agent Name</label>
              <input style={inputStyle} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Support Bot" />
            </div>
            <div>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Model</label>
              <select style={inputStyle} value={form.model} onChange={e => setForm({ ...form, model: e.target.value })}>
                <option value="">Select model...</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4-turbo">GPT-4 Turbo</option>
                <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                <option value="claude-3-opus">Claude 3 Opus</option>
                <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                <option value="gemini-pro">Gemini Pro</option>
              </select>
            </div>
          </div>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Description</label>
            <input style={inputStyle} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Brief description of this agent" />
          </div>
          <div style={{ marginBottom: '20px' }}>
            <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>System Prompt</label>
            <textarea
              style={{ ...inputStyle, height: '120px', resize: 'vertical' }}
              value={form.systemPrompt}
              onChange={e => setForm({ ...form, systemPrompt: e.target.value })}
              placeholder="Enter the system prompt for this agent..."
            />
          </div>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button onClick={() => setShowForm(false)} style={{
              padding: '9px 20px', borderRadius: '8px', border: '1px solid var(--border)',
              background: 'transparent', color: 'var(--text-primary)', fontSize: '13px', cursor: 'pointer',
            }}>Cancel</button>
            <button onClick={handleSave} style={{
              padding: '9px 20px', borderRadius: '8px', border: 'none',
              background: 'linear-gradient(135deg, #1e6bff, #3d8bff)',
              color: 'white', fontSize: '13px', cursor: 'pointer', fontWeight: 600,
            }}>Save Agent</button>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>Loading agents...</div>
      ) : agents.length === 0 ? (
        <div style={{
          background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)',
          padding: '60px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '14px',
        }}>No agents configured yet. Create your first agent above.</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
          {agents.map(agent => (
            <div key={agent.id} style={{
              background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)',
              padding: '20px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>{agent.name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{agent.description}</div>
                </div>
                <span style={{
                  padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, marginLeft: '12px', flexShrink: 0,
                  background: agent.isActive ? 'rgba(0,200,83,0.15)' : 'rgba(213,0,0,0.15)',
                  color: agent.isActive ? '#00c853' : '#d50000',
                }}>{agent.isActive ? 'Active' : 'Inactive'}</span>
              </div>
              <div style={{ marginBottom: '16px' }}>
                <span style={{
                  padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
                  background: 'rgba(30,107,255,0.15)', color: '#1e6bff',
                }}>{agent.model || 'No model'}</span>
              </div>
              {agent.systemPrompt && (
                <div style={{
                  background: 'var(--bg)', borderRadius: '6px', padding: '10px',
                  fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px',
                  maxHeight: '60px', overflow: 'hidden',
                }}>
                  {agent.systemPrompt}
                </div>
              )}
              <div style={{ display: 'flex', gap: '8px' }}>
                <button onClick={() => handleEdit(agent)} style={{
                  flex: 1, padding: '7px', borderRadius: '6px', border: '1px solid var(--border)',
                  background: 'transparent', color: 'var(--text-primary)', fontSize: '12px', cursor: 'pointer',
                }}>Edit</button>
                <button onClick={() => handleDelete(agent.id)} style={{
                  flex: 1, padding: '7px', borderRadius: '6px', border: 'none',
                  background: 'rgba(213,0,0,0.15)', color: '#d50000', fontSize: '12px', cursor: 'pointer',
                }}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Agents;
