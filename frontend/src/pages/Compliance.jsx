import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../utils/api'
import Spinner from '../components/Spinner'
import {
  ShieldCheck, Plus, Play, FileText, CheckCircle, AlertTriangle,
  XCircle, HelpCircle, Eye, Download, RefreshCw, ChevronDown,
  ChevronRight, Filter, Search, Clock, TrendingUp, X
} from 'lucide-react'

// ── Status badge colors & labels ──
const STATUS_CONFIG = {
  compliant: { color: '#22c55e', bg: '#22c55e22', label: 'Compliant', icon: CheckCircle },
  partial: { color: '#eab308', bg: '#eab30822', label: 'Partial', icon: AlertTriangle },
  non_compliant: { color: '#ef4444', bg: '#ef444422', label: 'Non-Compliant', icon: XCircle },
  not_applicable: { color: '#64748b', bg: '#64748b22', label: 'N/A', icon: HelpCircle },
  pending: { color: '#3b82f6', bg: '#3b82f622', label: 'Pending', icon: Clock },
}

const EVAL_STATUS_CONFIG = {
  created: { color: '#64748b', label: 'Created' },
  parsing_sotr: { color: '#8b5cf6', label: 'Parsing SOTR' },
  scoring: { color: '#f59e0b', label: 'Scoring' },
  completed: { color: '#22c55e', label: 'Completed' },
  failed: { color: '#ef4444', label: 'Failed' },
}

const REC_CONFIG = {
  accept: { color: '#22c55e', label: 'ACCEPT' },
  conditional: { color: '#f59e0b', label: 'CONDITIONAL' },
  reject: { color: '#ef4444', label: 'REJECT' },
}

function StatusBadge({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.pending
  const Icon = config.icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
      background: config.bg, color: config.color,
    }}>
      <Icon size={12} />
      {config.label}
    </span>
  )
}

function EvalStatusBadge({ status }) {
  const config = EVAL_STATUS_CONFIG[status] || EVAL_STATUS_CONFIG.created
  return (
    <span style={{
      padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
      background: config.color + '22', color: config.color,
    }}>
      {config.label}
    </span>
  )
}

function ScoreGauge({ score }) {
  const pct = ((score || 0) * 100).toFixed(1)
  const color = score >= 0.8 ? '#22c55e' : score >= 0.6 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 60, height: 6, borderRadius: 3, background: 'var(--border)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 3, background: color, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color }}>{pct}%</span>
    </div>
  )
}

export default function Compliance() {
  // State
  const [evaluations, setEvaluations] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedEval, setSelectedEval] = useState(null)
  const [evalDetail, setEvalDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [documents, setDocuments] = useState([])
  const [pollInterval, setPollInterval] = useState(null)

  // Create form state
  const [formSotrId, setFormSotrId] = useState('')
  const [formVendorId, setFormVendorId] = useState('')
  const [formProject, setFormProject] = useState('')
  const [formVessel, setFormVessel] = useState('')
  const [formVendor, setFormVendor] = useState('')
  const [creating, setCreating] = useState(false)

  // Filters
  const [statusFilter, setStatusFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    fetchEvaluations()
    fetchDocuments()
    return () => { if (pollInterval) clearInterval(pollInterval) }
  }, [])

  const fetchEvaluations = async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/compliance/evaluations?limit=50')
      if (data) setEvaluations(Array.isArray(data) ? data : [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const fetchDocuments = async () => {
    try {
      const data = await apiFetch('/documents/?limit=500')
      if (data && data.documents) setDocuments(data.documents)
    } catch (e) { console.error(e) }
  }

  const fetchEvalDetail = useCallback(async (evalId) => {
    setDetailLoading(true)
    try {
      const data = await apiFetch(`/compliance/evaluations/${evalId}?include_scores=true`)
      if (data) setEvalDetail(data)
    } catch (e) { console.error(e) }
    finally { setDetailLoading(false) }
  }, [])

  const handleSelectEval = (ev) => {
    setSelectedEval(ev)
    fetchEvalDetail(ev.id)
  }

  const handleCreateEvaluation = async () => {
    if (!formSotrId || !formVendorId) return
    setCreating(true)
    try {
      const resp = await apiFetch('/compliance/evaluations', {
        method: 'POST',
        body: JSON.stringify({
          sotr_doc_id: parseInt(formSotrId),
          vendor_doc_id: parseInt(formVendorId),
          project_name: formProject || null,
          vessel_name: formVessel || null,
          vendor_name: formVendor || null,
          auto_start: true,
        }),
      })
      if (resp) {
        setShowCreateModal(false)
        resetForm()
        fetchEvaluations()
        // Start polling for this eval
        startPolling(resp.id)
      }
    } catch (e) { console.error(e) }
    finally { setCreating(false) }
  }

  const handleRunEvaluation = async (evalId) => {
    try {
      await apiFetch(`/compliance/evaluations/${evalId}/run`, { method: 'POST' })
      fetchEvaluations()
      startPolling(evalId)
    } catch (e) { console.error(e) }
  }

  const handleGenerateReport = async (evalId) => {
    try {
      const data = await apiFetch(`/compliance/evaluations/${evalId}/report?format=pdf`)
      if (data && data.download_url) {
        window.open(`/api${data.download_url}`, '_blank')
      }
    } catch (e) { console.error(e) }
  }

  const startPolling = (evalId) => {
    if (pollInterval) clearInterval(pollInterval)
    const interval = setInterval(async () => {
      const data = await apiFetch(`/compliance/evaluations/${evalId}?include_scores=false`)
      if (data) {
        setEvaluations(prev => prev.map(e => e.id === evalId ? { ...e, ...data } : e))
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(interval)
          setPollInterval(null)
          fetchEvaluations()
          if (selectedEval && selectedEval.id === evalId) fetchEvalDetail(evalId)
        }
      }
    }, 3000)
    setPollInterval(interval)
  }

  const resetForm = () => {
    setFormSotrId('')
    setFormVendorId('')
    setFormProject('')
    setFormVessel('')
    setFormVendor('')
  }

  // Filtered evaluations
  const filtered = evaluations.filter(ev => {
    if (statusFilter && ev.status !== statusFilter) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (ev.project_name || '').toLowerCase().includes(q) ||
        (ev.vessel_name || '').toLowerCase().includes(q) ||
        (ev.vendor_name || '').toLowerCase().includes(q)
    }
    return true
  })

  if (loading) return <div style={{ padding: 40 }}><Spinner /></div>

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <ShieldCheck size={24} color="#3b82f6" />
            Compliance Evaluations
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '4px 0 0' }}>
            SOTR vs Vendor Submission compliance scoring
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={fetchEvaluations} style={btnSecondary}>
            <RefreshCw size={14} /> Refresh
          </button>
          <button onClick={() => setShowCreateModal(true)} style={btnPrimary}>
            <Plus size={14} /> New Evaluation
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1 1 200px', maxWidth: 300 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-secondary)' }} />
          <input
            placeholder="Search by project, vessel, vendor..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ ...inputStyle, paddingLeft: 30 }}
          />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={selectStyle}>
          <option value="">All statuses</option>
          {Object.entries(EVAL_STATUS_CONFIG).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
      </div>

      {/* Main content: List + Detail */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedEval ? '1fr 1.5fr' : '1fr', gap: 20 }}>
        {/* Evaluations List */}
        <div style={{ background: 'var(--surface)', borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
            Evaluations ({filtered.length})
          </div>
          <div style={{ maxHeight: 600, overflowY: 'auto' }}>
            {filtered.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>
                No evaluations found. Create one to get started.
              </div>
            ) : filtered.map(ev => (
              <div
                key={ev.id}
                onClick={() => handleSelectEval(ev)}
                style={{
                  padding: '14px 16px', borderBottom: '1px solid var(--border)',
                  cursor: 'pointer', transition: 'background 0.15s',
                  background: selectedEval?.id === ev.id ? 'var(--sidebar-active-bg)' : 'transparent',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>
                    {ev.project_name || `Evaluation #${ev.id}`}
                  </span>
                  <EvalStatusBadge status={ev.status} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {ev.vessel_name || 'No vessel'} {ev.vendor_name ? `• ${ev.vendor_name}` : ''}
                  </span>
                  {ev.overall_score != null && <ScoreGauge score={ev.overall_score} />}
                </div>
                {ev.total_clauses > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', gap: 8, fontSize: 11 }}>
                    <span style={{ color: '#22c55e' }}>{ev.compliant_count} C</span>
                    <span style={{ color: '#eab308' }}>{ev.partial_count} P</span>
                    <span style={{ color: '#ef4444' }}>{ev.non_compliant_count} NC</span>
                    <span style={{ color: '#64748b' }}>{ev.not_applicable_count} NA</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Detail Panel */}
        {selectedEval && (
          <div style={{ background: 'var(--surface)', borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
            {detailLoading ? (
              <div style={{ padding: 40 }}><Spinner /></div>
            ) : evalDetail ? (
              <EvalDetailPanel
                detail={evalDetail}
                onRun={() => handleRunEvaluation(evalDetail.id)}
                onReport={() => handleGenerateReport(evalDetail.id)}
                onRefresh={() => fetchEvalDetail(evalDetail.id)}
                onClose={() => { setSelectedEval(null); setEvalDetail(null) }}
              />
            ) : null}
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <ModalOverlay onClose={() => setShowCreateModal(false)}>
          <div style={{ width: 500, background: 'var(--surface)', borderRadius: 12, padding: 24, boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <h2 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700 }}>New Compliance Evaluation</h2>

            <label style={labelStyle}>SOTR Document *</label>
            <select value={formSotrId} onChange={e => setFormSotrId(e.target.value)} style={selectStyle}>
              <option value="">Select SOTR document...</option>
              {documents.filter(d => d.category?.toLowerCase().includes('sotr') || d.filename?.toLowerCase().includes('sotr'))
                .map(d => <option key={d.id} value={d.id}>{d.filename} (ID: {d.id})</option>)}
              <optgroup label="All Documents">
                {documents.map(d => <option key={d.id} value={d.id}>{d.filename} (ID: {d.id})</option>)}
              </optgroup>
            </select>

            <label style={labelStyle}>Vendor Submission *</label>
            <select value={formVendorId} onChange={e => setFormVendorId(e.target.value)} style={selectStyle}>
              <option value="">Select vendor document...</option>
              {documents.map(d => <option key={d.id} value={d.id}>{d.filename} (ID: {d.id})</option>)}
            </select>

            <label style={labelStyle}>Project Name</label>
            <input value={formProject} onChange={e => setFormProject(e.target.value)} placeholder="e.g. OPV Construction" style={inputStyle} />

            <label style={labelStyle}>Vessel Name</label>
            <input value={formVessel} onChange={e => setFormVessel(e.target.value)} placeholder="e.g. ICGS Sarthi" style={inputStyle} />

            <label style={labelStyle}>Vendor Name</label>
            <input value={formVendor} onChange={e => setFormVendor(e.target.value)} placeholder="e.g. ABC Shipyard Ltd" style={inputStyle} />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
              <button onClick={() => setShowCreateModal(false)} style={btnSecondary}>Cancel</button>
              <button
                onClick={handleCreateEvaluation}
                disabled={!formSotrId || !formVendorId || creating}
                style={{ ...btnPrimary, opacity: (!formSotrId || !formVendorId || creating) ? 0.5 : 1 }}
              >
                {creating ? 'Creating...' : 'Create & Start'}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  )
}

// ── Evaluation Detail Panel ──
function EvalDetailPanel({ detail, onRun, onReport, onRefresh, onClose }) {
  const [expandedClause, setExpandedClause] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState('')

  const scores = detail.clause_scores || []
  const filteredScores = scores.filter(s => {
    if (!categoryFilter) return true
    return s.clause?.category === categoryFilter
  })

  const categories = [...new Set(scores.map(s => s.clause?.category).filter(Boolean))]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', maxHeight: 700 }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
            {detail.project_name || `Evaluation #${detail.id}`}
          </h3>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            {detail.vessel_name || 'N/A'} • {detail.vendor_name || 'N/A'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <EvalStatusBadge status={detail.status} />
          <button onClick={onClose} style={{ ...btnIcon, marginLeft: 8 }}><X size={16} /></button>
        </div>
      </div>

      {/* Superseded document warnings */}
      {detail.warnings && detail.warnings.length > 0 && (
        <div style={{ padding: '10px 20px', background: '#fef3c7', borderBottom: '1px solid #f59e0b' }}>
          {detail.warnings.map((w, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#92400e', fontWeight: 500 }}>
              <AlertTriangle size={14} color="#f59e0b" />
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Summary Stats */}
      <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        {detail.overall_score != null && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Score:</span>
            <ScoreGauge score={detail.overall_score} />
          </div>
        )}
        {detail.recommendation && (
          <span style={{
            padding: '3px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700,
            background: (REC_CONFIG[detail.recommendation]?.color || '#64748b') + '22',
            color: REC_CONFIG[detail.recommendation]?.color || '#64748b',
          }}>
            {REC_CONFIG[detail.recommendation]?.label || detail.recommendation.toUpperCase()}
          </span>
        )}
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {detail.total_clauses} clauses
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {detail.status === 'created' && (
            <button onClick={onRun} style={btnPrimary}><Play size={12} /> Run</button>
          )}
          {detail.status === 'completed' && (
            <button onClick={onReport} style={btnSecondary}><Download size={12} /> PDF</button>
          )}
          <button onClick={onRefresh} style={btnIcon}><RefreshCw size={14} /></button>
        </div>
      </div>

      {/* Missing clauses warning */}
      {detail.clause_scores?.filter(s => s.is_missing).length > 0 && (
        <div style={{ padding: '8px 20px', borderBottom: '1px solid var(--border)', background: '#fef2f2', display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertTriangle size={14} color="#dc2626" />
          <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>
            {detail.clause_scores.filter(s => s.is_missing).length} clause(s) missing from vendor submission
          </span>
          <span style={{ fontSize: 11, color: '#7f1d1d' }}>
            — Vendor has silently skipped these requirements
          </span>
        </div>
      )}

      {/* Category filter */}
      {categories.length > 0 && (
        <div style={{ padding: '8px 20px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button
            onClick={() => setCategoryFilter('')}
            style={{ ...chipBtn, background: !categoryFilter ? 'var(--accent-blue)' : 'var(--border)', color: !categoryFilter ? '#fff' : 'var(--text-secondary)' }}
          >All</button>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              style={{ ...chipBtn, background: categoryFilter === cat ? 'var(--accent-blue)' : 'var(--border)', color: categoryFilter === cat ? '#fff' : 'var(--text-secondary)' }}
            >{cat}</button>
          ))}
        </div>
      )}

      {/* Clause Scores */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {filteredScores.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>
            {detail.status === 'completed' ? 'No clauses match filter.' : 'Evaluation not yet run. Click "Run" to start scoring.'}
          </div>
        ) : filteredScores.map(score => (
          <div key={score.id} style={{ borderBottom: '1px solid var(--border)' }}>
            {/* Clause row */}
            <div
              onClick={() => setExpandedClause(expandedClause === score.id ? null : score.id)}
              style={{ padding: '10px 20px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10, transition: 'background 0.1s' }}
            >
              {expandedClause === score.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span style={{ fontWeight: 600, fontSize: 12, color: 'var(--text-secondary)', width: 50, flexShrink: 0 }}>
                {score.clause?.clause_number || '—'}
              </span>
              <span style={{ flex: 1, fontSize: 13, color: 'var(--text-primary)' }}>
                {score.clause?.clause_title || score.clause?.clause_text?.slice(0, 60) || 'Untitled'}
              </span>
              <StatusBadge status={score.status} />
              {score.is_missing && (
                <span style={{ padding: '2px 6px', borderRadius: 3, fontSize: 10, fontWeight: 700, background: '#dc262622', color: '#dc2626', border: '1px solid #dc262644' }}>
                  MISSING
                </span>
              )}
              <span style={{ fontSize: 11, color: 'var(--text-secondary)', width: 40, textAlign: 'right' }}>
                {(score.confidence * 100).toFixed(0)}%
              </span>
            </div>

            {/* Expanded detail */}
            {expandedClause === score.id && (
              <div style={{ padding: '0 20px 14px 54px', fontSize: 12, lineHeight: 1.6 }}>
                {score.is_missing && (
                  <div style={{ marginBottom: 10, padding: '8px 12px', borderRadius: 6, background: '#fef2f2', border: '1px solid #fecaca', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <AlertTriangle size={14} color="#dc2626" style={{ marginTop: 2, flexShrink: 0 }} />
                    <div>
                      <strong style={{ color: '#dc2626', fontSize: 12 }}>Vendor Skipped This Clause</strong>
                      <p style={{ margin: '2px 0 0', color: '#7f1d1d', fontSize: 11 }}>
                        The vendor submission contains no text addressing this {score.clause?.is_critical ? 'CRITICAL ' : ''}{score.clause?.is_mandatory ? 'mandatory ' : ''}requirement. This may indicate the vendor has silently omitted compliance with this clause.
                      </p>
                    </div>
                  </div>
                )}
                {score.clause?.clause_text && (
                  <div style={{ marginBottom: 8 }}>
                    <strong style={{ color: 'var(--text-secondary)' }}>Requirement:</strong>
                    <p style={{ margin: '2px 0', color: 'var(--text-primary)' }}>{score.clause.clause_text}</p>
                  </div>
                )}
                {score.vendor_response_summary && (
                  <div style={{ marginBottom: 8 }}>
                    <strong style={{ color: 'var(--text-secondary)' }}>Vendor Response:</strong>
                    <p style={{ margin: '2px 0', color: 'var(--text-primary)' }}>{score.vendor_response_summary}</p>
                  </div>
                )}
                {score.evidence_text && (
                  <div style={{ marginBottom: 8, background: 'var(--bg)', padding: 8, borderRadius: 6, borderLeft: '3px solid var(--border)' }}>
                    <strong style={{ color: 'var(--text-secondary)' }}>Evidence:</strong>
                    <p style={{ margin: '2px 0', color: 'var(--text-primary)', fontStyle: 'italic' }}>{score.evidence_text}</p>
                  </div>
                )}
                {score.gaps_identified && (
                  <div style={{ marginBottom: 8 }}>
                    <strong style={{ color: '#ef4444' }}>Gaps:</strong>
                    <p style={{ margin: '2px 0', color: 'var(--text-primary)' }}>{score.gaps_identified}</p>
                  </div>
                )}
                {score.manually_reviewed && (
                  <div style={{ fontSize: 11, color: '#8b5cf6', fontWeight: 500 }}>
                    Manually reviewed {score.reviewer_notes ? `— ${score.reviewer_notes}` : ''}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Modal Overlay ──
function ModalOverlay({ children, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
    >
      <div onClick={e => e.stopPropagation()}>{children}</div>
    </div>
  )
}

// ── Shared styles ──
const btnPrimary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 14px', borderRadius: 8, border: 'none',
  background: '#3b82f6', color: '#fff', fontSize: 13, fontWeight: 600,
  cursor: 'pointer', transition: 'opacity 0.15s',
}

const btnSecondary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 14px', borderRadius: 8,
  border: '1px solid var(--border)', background: 'var(--surface)',
  color: 'var(--text-primary)', fontSize: 13, fontWeight: 500,
  cursor: 'pointer',
}

const btnIcon = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  width: 32, height: 32, borderRadius: 6,
  border: '1px solid var(--border)', background: 'transparent',
  color: 'var(--text-secondary)', cursor: 'pointer',
}

const chipBtn = {
  padding: '4px 10px', borderRadius: 12, border: 'none',
  fontSize: 11, fontWeight: 600, cursor: 'pointer',
  transition: 'all 0.15s',
}

const inputStyle = {
  width: '100%', padding: '9px 12px', borderRadius: 8,
  border: '1px solid var(--border)', background: 'var(--bg)',
  color: 'var(--text-primary)', fontSize: 13, marginBottom: 12,
  outline: 'none', boxSizing: 'border-box',
}

const selectStyle = {
  padding: '9px 12px', borderRadius: 8,
  border: '1px solid var(--border)', background: 'var(--bg)',
  color: 'var(--text-primary)', fontSize: 13, marginBottom: 12,
  outline: 'none', minWidth: 150,
}

const labelStyle = {
  display: 'block', fontSize: 12, fontWeight: 600,
  color: 'var(--text-secondary)', marginBottom: 4,
}
