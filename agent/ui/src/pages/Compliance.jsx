/**
 * AGRA Compliance Module — Compliance Evaluation Page
 * Phase 5: SOTR vs Vendor Submission Evaluation UI
 * 
 * Features:
 * - Evaluation Setup: Select SOTR, upload vendor doc
 * - Clause Review: View and edit clause scores
 * - Summary Dashboard: Compliance statistics
 * - Report Generation: PDF export
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck, FileText, Upload, CheckCircle, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, Download, Play, Loader2, ArrowLeft,
  Check, AlertCircle, Minus, ChevronRight, ChevronLeft, Plus,
  RefreshCw, FileCheck, BarChart3, PieChart, List, Filter
} from 'lucide-react';
import { getToken, getUser, getDashboardUrl } from '../utils/auth';
import api, { backendApi } from '../utils/api';
import { useTheme } from '../utils/ThemeContext';

// ── Status Badge Component ──
function StatusBadge({ status, confidence }) {
  const styles = {
    compliant: { bg: 'rgba(34, 197, 94, 0.15)', text: '#22c55e', icon: CheckCircle },
    partial: { bg: 'rgba(234, 179, 8, 0.15)', text: '#eab308', icon: AlertTriangle },
    non_compliant: { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', icon: XCircle },
    not_applicable: { bg: 'rgba(156, 163, 175, 0.15)', text: '#9ca3af', icon: Minus },
    pending: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', icon: Loader2 },
  };

  const style = styles[status] || styles.pending;
  const Icon = style.icon;

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '4px 10px',
      borderRadius: '20px',
      background: style.bg,
      color: style.text,
      fontSize: '12px',
      fontWeight: 600,
      textTransform: 'capitalize'
    }}>
      <Icon size={12} />
      {status.replace('_', '-')}
      {confidence !== undefined && (
        <span style={{ opacity: 0.8, marginLeft: '4px' }}>
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
}

// ── Progress Bar ──
function ProgressBar({ percent, color = '#22c55e' }) {
  return (
    <div style={{ width: '100%', height: '8px', background: 'var(--border)', borderRadius: '4px', overflow: 'hidden' }}>
      <div style={{
        width: `${percent}%`,
        height: '100%',
        background: color,
        borderRadius: '4px',
        transition: 'width 0.3s ease'
      }} />
    </div>
  );
}

// ── Main Compliance Page ──
export default function Compliance() {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  
  // ── State ──
  const [activeTab, setActiveTab] = useState('setup'); // setup, review, summary
  const [evaluations, setEvaluations] = useState([]);
  const [selectedEval, setSelectedEval] = useState(null);
  const [evalDetails, setEvalDetails] = useState(null);
  const [sotrDocs, setSotrDocs] = useState([]);
  const [vendorFile, setVendorFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  
  // Form state
  const [formData, setFormData] = useState({
    sotr_doc_id: '',
    project_name: '',
    vessel_name: '',
    vendor_name: ''
  });

  // ── Auth Check ──
  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate('/');
      return;
    }
    
    const user = getUser();
    if (user?.role === 'super_admin' || user?.is_superadmin) {
      setIsSuperAdmin(true);
    }
  }, [navigate]);

  // ── Fetch Data ──
  const fetchEvaluations = useCallback(async () => {
    try {
      const res = await backendApi.get('/compliance/evaluations?limit=20');
      setEvaluations(res.data || []);
    } catch (err) {
      console.error('Failed to fetch evaluations:', err);
    }
  }, []);

  const fetchSotrDocuments = useCallback(async () => {
    try {
      // Get documents and filter for SOTR type
      const res = await api.get('/documents?limit=100');
      const docs = res.data?.documents || [];
      // Filter for likely SOTR docs (based on filename/content type)
      const sotrDocs = docs.filter(d => 
        d.category?.toLowerCase().includes('standard') ||
        d.filename?.toLowerCase().includes('sotr') ||
        d.filename?.toLowerCase().includes('technical')
      );
      setSotrDocs(sotrDocs);
    } catch (err) {
      console.error('Failed to fetch SOTR docs:', err);
    }
  }, []);

  useEffect(() => {
    fetchEvaluations();
    fetchSotrDocuments();
  }, [fetchEvaluations, fetchSotrDocuments]);

  // ── Handlers ──
  const handleCreateEvaluation = async () => {
    if (!formData.sotr_doc_id || !vendorFile) {
      setError('Please select both SOTR document and vendor submission');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // First upload vendor document
      const uploadForm = new FormData();
      uploadForm.append('file', vendorFile);
      uploadForm.append('source', 'vendor_submission');
      
      const uploadRes = await api.post('/upload', uploadForm, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      const vendorDocId = uploadRes.data?.doc_id;
      if (!vendorDocId) {
        throw new Error('Failed to upload vendor document');
      }

      // Create evaluation
      const evalRes = await backendApi.post('/compliance/evaluations', {
        sotr_doc_id: parseInt(formData.sotr_doc_id),
        vendor_doc_id: vendorDocId,
        project_name: formData.project_name,
        vessel_name: formData.vessel_name,
        vendor_name: formData.vendor_name,
        auto_start: true
      });

      setSelectedEval(evalRes.data);
      setActiveTab('review');
      fetchEvaluations();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to create evaluation');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunEvaluation = async (evalId) => {
    setIsLoading(true);
    try {
      await backendApi.post(`/compliance/evaluations/${evalId}/run`);
      // Poll for completion
      pollEvaluationStatus(evalId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run evaluation');
      setIsLoading(false);
    }
  };

  const pollEvaluationStatus = async (evalId) => {
    const checkStatus = async () => {
      try {
        const res = await backendApi.get(`/compliance/evaluations/${evalId}`);
        setEvalDetails(res.data);
        
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          setIsLoading(false);
          return;
        }
        
        // Continue polling
        setTimeout(checkStatus, 3000);
      } catch (err) {
        console.error('Poll error:', err);
        setIsLoading(false);
      }
    };
    
    checkStatus();
  };

  const handleScoreClause = async (evalId, clauseId, status, notes = '') => {
    try {
      await backendApi.post(`/compliance/evaluations/${evalId}/score`, {
        clause_id: clauseId,
        status: status,
        notes: notes,
        confidence: 1.0 // Manual override = high confidence
      });
      
      // Refresh evaluation details
      const res = await backendApi.get(`/compliance/evaluations/${evalId}?include_scores=true`);
      setEvalDetails(res.data);
    } catch (err) {
      console.error('Failed to score clause:', err);
    }
  };

  const handleGenerateReport = async (evalId) => {
    try {
      const res = await backendApi.get(`/compliance/evaluations/${evalId}/report?format=pdf`);
      if (res.data?.download_url) {
        window.open(res.data.download_url, '_blank');
      }
    } catch (err) {
      console.error('Failed to generate report:', err);
    }
  };

  // ── Render ──
  return (
    <div style={{ ...styles.layout, background: isDark ? '#0f172a' : '#f1f5f9' }}>
      {/* ── Sidebar ── */}
      <aside style={{ 
        ...styles.sidebar, 
        width: sidebarCollapsed ? '60px' : '260px',
        background: isDark ? '#1e293b' : '#fff',
        borderColor: isDark ? '#334155' : '#e2e8f0'
      }}>
        <div style={{ ...styles.sidebarHeader, borderColor: isDark ? '#334155' : '#e2e8f0' }}>
          <div style={styles.logoGroup}>
            <div style={styles.logoIcon}><ShieldCheck size={20} color="#4a8bff" /></div>
            {!sidebarCollapsed && (
              <div>
                <div style={{ ...styles.logoText, color: isDark ? '#fff' : '#1e293b' }}>AGRA</div>
                <div style={styles.logoSub}>Compliance</div>
              </div>
            )}
          </div>
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} style={styles.collapseBtn}>
            {sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>

        {/* Navigation Links */}
        <div style={styles.navSection}>
          <Link to="/" style={{ ...styles.navLink, color: isDark ? '#94a3b8' : '#64748b' }}>
            <ArrowLeft size={15} />
            {!sidebarCollapsed && <span>Back to Chat</span>}
          </Link>
          
          {isSuperAdmin && (
            <a href={getDashboardUrl('/dashboard')} style={{ ...styles.navLink, color: isDark ? '#94a3b8' : '#64748b' }}>
              <BarChart3 size={15} />
              {!sidebarCollapsed && <span>Dashboard</span>}
            </a>
          )}
        </div>

        {/* Recent Evaluations */}
        {!sidebarCollapsed && evaluations.length > 0 && (
          <div style={styles.section}>
            <div style={{ ...styles.sectionTitle, color: isDark ? '#64748b' : '#94a3b8' }}>
              Recent Evaluations
            </div>
            {evaluations.slice(0, 5).map(evalItem => (
              <div 
                key={evalItem.id}
                onClick={() => { setSelectedEval(evalItem); setActiveTab('review'); }}
                style={{
                  ...styles.evalItem,
                  background: selectedEval?.id === evalItem.id ? (isDark ? '#334155' : '#e2e8f0') : 'transparent'
                }}
              >
                <FileText size={14} color={isDark ? '#94a3b8' : '#64748b'} />
                <div style={styles.evalInfo}>
                  <div style={{ fontSize: '11px', color: isDark ? '#e2e8f0' : '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {evalItem.vessel_name || `Eval #${evalItem.id}`}
                  </div>
                  <StatusBadge status={evalItem.status} />
                </div>
              </div>
            ))}
          </div>
        )}
      </aside>

      {/* ── Main Content ── */}
      <main style={{ ...styles.main, background: isDark ? '#0f172a' : '#f1f5f9' }}>
        {/* Header */}
        <header style={{ ...styles.header, background: isDark ? '#1e293b' : '#fff', borderColor: isDark ? '#334155' : '#e2e8f0' }}>
          <div style={styles.headerTitle}>
            <FileCheck size={24} color="#4a8bff" />
            <div>
              <h1 style={{ ...styles.title, color: isDark ? '#fff' : '#1e293b' }}>
                Compliance Evaluation
              </h1>
              <p style={{ ...styles.subtitle, color: isDark ? '#94a3b8' : '#64748b' }}>
                SOTR vs Vendor Submission Analysis
              </p>
            </div>
          </div>
          
          {/* Tab Navigation */}
          <div style={styles.tabs}>
            {['setup', 'review', 'summary'].map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  ...styles.tab,
                  color: activeTab === tab ? '#4a8bff' : (isDark ? '#94a3b8' : '#64748b'),
                  borderBottomColor: activeTab === tab ? '#4a8bff' : 'transparent'
                }}
              >
                {tab === 'setup' && <Upload size={16} />}
                {tab === 'review' && <List size={16} />}
                {tab === 'summary' && <PieChart size={16} />}
                <span style={{ textTransform: 'capitalize' }}>{tab}</span>
              </button>
            ))}
          </div>
        </header>

        {/* Content Area */}
        <div style={styles.content}>
          {error && (
            <div style={styles.errorAlert}>
              <AlertCircle size={18} />
              {error}
              <button onClick={() => setError(null)} style={styles.closeBtn}>×</button>
            </div>
          )}

          {/* ── SETUP TAB ── */}
          {activeTab === 'setup' && (
            <div style={styles.panel}>
              <h2 style={{ ...styles.panelTitle, color: isDark ? '#fff' : '#1e293b' }}>
                New Evaluation
              </h2>
              
              <div style={styles.formGrid}>
                {/* SOTR Selection */}
                <div style={styles.formGroup}>
                  <label style={{ ...styles.label, color: isDark ? '#cbd5e1' : '#475569' }}>
                    SOTR Document *
                  </label>
                  <select
                    value={formData.sotr_doc_id}
                    onChange={(e) => setFormData({...formData, sotr_doc_id: e.target.value})}
                    style={{ ...styles.select, background: isDark ? '#334155' : '#fff', color: isDark ? '#fff' : '#1e293b' }}
                  >
                    <option value="">Select SOTR...</option>
                    {sotrDocs.map(doc => (
                      <option key={doc.id} value={doc.id}>
                        {doc.filename} ({doc.category})
                      </option>
                    ))}
                  </select>
                  {sotrDocs.length === 0 && (
                    <p style={{ fontSize: '12px', color: '#eab308', marginTop: '4px' }}>
                      No SOTR documents found. Upload an SOTR first.
                    </p>
                  )}
                </div>

                {/* Project Name */}
                <div style={styles.formGroup}>
                  <label style={{ ...styles.label, color: isDark ? '#cbd5e1' : '#475569' }}>
                    Project Name
                  </label>
                  <input
                    type="text"
                    value={formData.project_name}
                    onChange={(e) => setFormData({...formData, project_name: e.target.value})}
                    placeholder="e.g., OPV Construction Project"
                    style={{ ...styles.input, background: isDark ? '#334155' : '#fff', color: isDark ? '#fff' : '#1e293b' }}
                  />
                </div>

                {/* Vessel Name */}
                <div style={styles.formGroup}>
                  <label style={{ ...styles.label, color: isDark ? '#cbd5e1' : '#475569' }}>
                    Vessel Name
                  </label>
                  <input
                    type="text"
                    value={formData.vessel_name}
                    onChange={(e) => setFormData({...formData, vessel_name: e.target.value})}
                    placeholder="e.g., ICGS Sarthi"
                    style={{ ...styles.input, background: isDark ? '#334155' : '#fff', color: isDark ? '#fff' : '#1e293b' }}
                  />
                </div>

                {/* Vendor Name */}
                <div style={styles.formGroup}>
                  <label style={{ ...styles.label, color: isDark ? '#cbd5e1' : '#475569' }}>
                    Vendor Name
                  </label>
                  <input
                    type="text"
                    value={formData.vendor_name}
                    onChange={(e) => setFormData({...formData, vendor_name: e.target.value})}
                    placeholder="e.g., ABC Shipyard Ltd"
                    style={{ ...styles.input, background: isDark ? '#334155' : '#fff', color: isDark ? '#fff' : '#1e293b' }}
                  />
                </div>
              </div>

              {/* Vendor Document Upload */}
              <div style={{ ...styles.uploadArea, borderColor: isDark ? '#334155' : '#e2e8f0' }}>
                <label style={{ ...styles.label, color: isDark ? '#cbd5e1' : '#475569' }}>
                  Vendor Submission Document *
                </label>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx"
                  onChange={(e) => setVendorFile(e.target.files?.[0] || null)}
                  style={styles.fileInput}
                />
                {vendorFile && (
                  <div style={styles.filePreview}>
                    <FileText size={20} color="#4a8bff" />
                    <span style={{ color: isDark ? '#fff' : '#1e293b' }}>{vendorFile.name}</span>
                  </div>
                )}
              </div>

              {/* Submit Button */}
              <button
                onClick={handleCreateEvaluation}
                disabled={isLoading || !formData.sotr_doc_id || !vendorFile}
                style={{
                  ...styles.submitBtn,
                  opacity: isLoading || !formData.sotr_doc_id || !vendorFile ? 0.6 : 1,
                  cursor: isLoading || !formData.sotr_doc_id || !vendorFile ? 'not-allowed' : 'pointer'
                }}
              >
                {isLoading ? <Loader2 size={18} className="spin" /> : <Play size={18} />}
                {isLoading ? 'Creating...' : 'Start Evaluation'}
              </button>
            </div>
          )}

          {/* ── REVIEW TAB ── */}
          {activeTab === 'review' && selectedEval && (
            <div style={styles.panel}>
              <div style={styles.reviewHeader}>
                <div>
                  <h2 style={{ ...styles.panelTitle, color: isDark ? '#fff' : '#1e293b' }}>
                    Clause Review: {selectedEval.vessel_name || `Eval #${selectedEval.id}`}
                  </h2>
                  <div style={styles.metaRow}>
                    <StatusBadge status={selectedEval.status} />
                    {selectedEval.overall_score !== null && (
                      <span style={{ color: isDark ? '#94a3b8' : '#64748b' }}>
                        Overall Score: {(selectedEval.overall_score * 100).toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>
                
                {selectedEval.status !== 'completed' && selectedEval.status !== 'scoring' && (
                  <button
                    onClick={() => handleRunEvaluation(selectedEval.id)}
                    disabled={isLoading}
                    style={styles.actionBtn}
                  >
                    {isLoading ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
                    Run Evaluation
                  </button>
                )}
              </div>

              {isLoading && (
                <div style={styles.loadingOverlay}>
                  <Loader2 size={32} color="#4a8bff" className="spin" />
                  <p style={{ color: isDark ? '#94a3b8' : '#64748b' }}>
                    Processing compliance evaluation...
                  </p>
                </div>
              )}

              {evalDetails?.clause_scores?.length > 0 ? (
                <div style={styles.clauseList}>
                  {evalDetails.clause_scores.map((score) => (
                    <div 
                      key={score.id} 
                      style={{ ...styles.clauseCard, background: isDark ? '#1e293b' : '#fff' }}
                    >
                      <div style={styles.clauseHeader}>
                        <div style={styles.clauseId}>
                          <span style={{ fontWeight: 600, color: '#4a8bff' }}>
                            {score.clause?.clause_number || 'N/A'}
                          </span>
                          <span style={{ color: isDark ? '#94a3b8' : '#64748b', fontSize: '13px' }}>
                            {score.clause?.clause_title || 'Untitled'}
                          </span>
                        </div>
                        <StatusBadge status={score.status} confidence={score.confidence} />
                      </div>
                      
                      <p style={{ ...styles.clauseText, color: isDark ? '#cbd5e1' : '#475569' }}>
                        {score.clause?.clause_text?.substring(0, 150)}...
                      </p>

                      {score.evidence_text && (
                        <div style={{ ...styles.evidenceBox, background: isDark ? '#0f172a' : '#f8fafc' }}>
                          <span style={{ fontSize: '11px', color: '#4a8bff', fontWeight: 600 }}>
                            Evidence:
                          </span>
                          <p style={{ fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b', margin: 0 }}>
                            {score.evidence_text?.substring(0, 200)}...
                          </p>
                        </div>
                      )}

                      {score.gaps_identified && (
                        <div style={{ ...styles.gapsBox, background: 'rgba(239, 68, 68, 0.1)' }}>
                          <span style={{ fontSize: '11px', color: '#ef4444', fontWeight: 600 }}>
                            Gaps:
                          </span>
                          <p style={{ fontSize: '12px', color: '#ef4444', margin: 0 }}>
                            {score.gaps_identified}
                          </p>
                        </div>
                      )}

                      {/* Manual Override */}
                      <div style={styles.overrideRow}>
                        <span style={{ fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b' }}>
                          Manual Override:
                        </span>
                        <div style={styles.statusButtons}>
                          {['compliant', 'partial', 'non_compliant', 'not_applicable'].map(status => (
                            <button
                              key={status}
                              onClick={() => handleScoreClause(selectedEval.id, score.clause_id, status)}
                              style={{
                                ...styles.statusBtn,
                                background: score.status === status ? 
                                  (status === 'compliant' ? '#22c55e' : 
                                   status === 'partial' ? '#eab308' :
                                   status === 'non_compliant' ? '#ef4444' : '#9ca3af') : 
                                  (isDark ? '#334155' : '#e2e8f0'),
                                color: score.status === status ? '#fff' : (isDark ? '#cbd5e1' : '#475569')
                              }}
                            >
                              {status.replace('_', ' ')}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={styles.emptyState}>
                  <FileText size={48} color={isDark ? '#334155' : '#cbd5e1'} />
                  <p style={{ color: isDark ? '#94a3b8' : '#64748b' }}>
                    No clauses to review. Run the evaluation to analyze clauses.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ── SUMMARY TAB ── */}
          {activeTab === 'summary' && selectedEval && (
            <div style={styles.panel}>
              <h2 style={{ ...styles.panelTitle, color: isDark ? '#fff' : '#1e293b' }}>
                Compliance Summary
              </h2>

              {selectedEval.status === 'completed' ? (
                <>
                  {/* Overall Score */}
                  <div style={{ ...styles.scoreCard, background: isDark ? '#1e293b' : '#fff' }}>
                    <div style={styles.scoreHeader}>
                      <div>
                        <h3 style={{ margin: 0, color: isDark ? '#fff' : '#1e293b' }}>
                          Overall Compliance Score
                        </h3>
                        <p style={{ margin: '4px 0 0', color: isDark ? '#94a3b8' : '#64748b' }}>
                          {selectedEval.total_clauses} clauses evaluated
                        </p>
                      </div>
                      <div style={styles.bigScore}>
                        <span style={{ 
                          fontSize: '48px', 
                          fontWeight: 700, 
                          color: selectedEval.overall_score >= 0.8 ? '#22c55e' : 
                                 selectedEval.overall_score >= 0.6 ? '#eab308' : '#ef4444'
                        }}>
                          {(selectedEval.overall_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <ProgressBar 
                      percent={selectedEval.overall_score * 100} 
                      color={selectedEval.overall_score >= 0.8 ? '#22c55e' : 
                             selectedEval.overall_score >= 0.6 ? '#eab308' : '#ef4444'}
                    />
                  </div>

                  {/* Counts Grid */}
                  <div style={styles.countsGrid}>
                    {[
                      { label: 'Compliant', count: selectedEval.compliant_count || 0, color: '#22c55e' },
                      { label: 'Partial', count: selectedEval.partial_count || 0, color: '#eab308' },
                      { label: 'Non-Compliant', count: selectedEval.non_compliant_count || 0, color: '#ef4444' },
                      { label: 'Not Applicable', count: selectedEval.not_applicable_count || 0, color: '#9ca3af' },
                    ].map(item => (
                      <div key={item.label} style={{ ...styles.countCard, background: isDark ? '#1e293b' : '#fff' }}>
                        <span style={{ fontSize: '32px', fontWeight: 700, color: item.color }}>
                          {item.count}
                        </span>
                        <span style={{ fontSize: '13px', color: isDark ? '#94a3b8' : '#64748b' }}>
                          {item.label}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Recommendation */}
                  <div style={{ 
                    ...styles.recommendationBox, 
                    background: selectedEval.recommendation === 'accept' ? 'rgba(34, 197, 94, 0.1)' :
                                selectedEval.recommendation === 'conditional' ? 'rgba(234, 179, 8, 0.1)' :
                                'rgba(239, 68, 68, 0.1)',
                    borderColor: selectedEval.recommendation === 'accept' ? '#22c55e' :
                                selectedEval.recommendation === 'conditional' ? '#eab308' :
                                '#ef4444'
                  }}>
                    <h4 style={{ 
                      margin: '0 0 8px', 
                      color: selectedEval.recommendation === 'accept' ? '#22c55e' :
                            selectedEval.recommendation === 'conditional' ? '#eab308' :
                            '#ef4444'
                    }}>
                      Recommendation: {selectedEval.recommendation?.toUpperCase()}
                    </h4>
                    <p style={{ margin: 0, color: isDark ? '#94a3b8' : '#64748b' }}>
                      {selectedEval.recommendation === 'accept' 
                        ? 'Vendor submission meets all SOTR requirements.'
                        : selectedEval.recommendation === 'conditional'
                        ? 'Vendor submission meets most requirements with minor gaps.'
                        : 'Vendor submission has significant non-compliance issues.'}
                    </p>
                  </div>

                  {/* Generate Report Button */}
                  <button
                    onClick={() => handleGenerateReport(selectedEval.id)}
                    style={styles.reportBtn}
                  >
                    <Download size={18} />
                    Generate PDF Report
                  </button>
                </>
              ) : (
                <div style={styles.emptyState}>
                  <PieChart size={48} color={isDark ? '#334155' : '#cbd5e1'} />
                  <p style={{ color: isDark ? '#94a3b8' : '#64748b' }}>
                    Summary will be available after evaluation is completed.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* No Selection State */}
          {!selectedEval && activeTab !== 'setup' && (
            <div style={styles.emptyState}>
              <FileCheck size={48} color={isDark ? '#334155' : '#cbd5e1'} />
              <p style={{ color: isDark ? '#94a3b8' : '#64748b' }}>
                Select an evaluation from the sidebar or create a new one.
              </p>
              <button onClick={() => setActiveTab('setup')} style={styles.actionBtn}>
                <Plus size={16} />
                New Evaluation
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

// ── Styles ──
const styles = {
  layout: {
    display: 'flex',
    height: '100vh',
    overflow: 'hidden',
  },
  sidebar: {
    display: 'flex',
    flexDirection: 'column',
    borderRight: '1px solid',
    transition: 'width 0.2s ease',
    overflow: 'hidden',
  },
  sidebarHeader: {
    padding: '14px 12px 10px',
    borderBottom: '1px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  logoGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '9px',
  },
  logoIcon: {
    width: 34,
    height: 34,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '9px',
    background: 'rgba(74,139,255,0.12)',
    flexShrink: 0,
  },
  logoText: {
    fontSize: '15px',
    fontWeight: 800,
    letterSpacing: '1.5px',
  },
  logoSub: {
    fontSize: '9px',
    color: '#64748b',
    fontWeight: 500,
    letterSpacing: '0.3px',
  },
  collapseBtn: {
    background: 'transparent',
    border: 'none',
    color: '#64748b',
    padding: '4px',
    borderRadius: '6px',
    cursor: 'pointer',
    display: 'flex',
    opacity: 0.7,
  },
  navSection: {
    padding: '10px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  navLink: {
    display: 'flex',
    alignItems: 'center',
    gap: '9px',
    padding: '8px 12px',
    borderRadius: '8px',
    fontSize: '13px',
    textDecoration: 'none',
    transition: 'background 0.15s',
  },
  section: {
    padding: '10px',
    flex: 1,
    overflowY: 'auto',
  },
  sectionTitle: {
    fontSize: '10px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    padding: '0 8px 8px',
  },
  evalItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  evalInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    flex: 1,
    minWidth: 0,
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    padding: '16px 24px',
    borderBottom: '1px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  title: {
    margin: 0,
    fontSize: '20px',
    fontWeight: 600,
  },
  subtitle: {
    margin: '2px 0 0',
    fontSize: '13px',
  },
  tabs: {
    display: 'flex',
    gap: '4px',
  },
  tab: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 16px',
    border: 'none',
    background: 'transparent',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
    borderBottom: '2px solid',
    transition: 'all 0.15s',
  },
  content: {
    flex: 1,
    overflow: 'auto',
    padding: '24px',
  },
  panel: {
    maxWidth: '900px',
    margin: '0 auto',
  },
  panelTitle: {
    margin: '0 0 24px',
    fontSize: '18px',
    fontWeight: 600,
  },
  formGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '16px',
    marginBottom: '20px',
  },
  formGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  label: {
    fontSize: '13px',
    fontWeight: 500,
  },
  select: {
    padding: '10px 12px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '14px',
    outline: 'none',
  },
  input: {
    padding: '10px 12px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '14px',
    outline: 'none',
  },
  uploadArea: {
    padding: '20px',
    border: '2px dashed',
    borderRadius: '8px',
    marginBottom: '20px',
  },
  fileInput: {
    marginTop: '8px',
  },
  filePreview: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginTop: '12px',
    padding: '8px 12px',
    background: 'rgba(74,139,255,0.1)',
    borderRadius: '6px',
  },
  submitBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '12px 24px',
    background: '#4a8bff',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  errorAlert: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '12px 16px',
    background: 'rgba(239, 68, 68, 0.1)',
    color: '#ef4444',
    borderRadius: '8px',
    marginBottom: '16px',
    fontSize: '14px',
  },
  closeBtn: {
    marginLeft: 'auto',
    background: 'transparent',
    border: 'none',
    color: '#ef4444',
    fontSize: '18px',
    cursor: 'pointer',
  },
  reviewHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '20px',
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginTop: '8px',
  },
  actionBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '8px 16px',
    background: '#4a8bff',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
  },
  loadingOverlay: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px',
    gap: '16px',
  },
  clauseList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  clauseCard: {
    padding: '16px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
  },
  clauseHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  clauseId: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  clauseText: {
    fontSize: '14px',
    lineHeight: 1.5,
    margin: '0 0 12px',
  },
  evidenceBox: {
    padding: '10px 12px',
    borderRadius: '6px',
    marginBottom: '10px',
  },
  gapsBox: {
    padding: '10px 12px',
    borderRadius: '6px',
    marginBottom: '10px',
  },
  overrideRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    paddingTop: '12px',
    borderTop: '1px solid #e2e8f0',
  },
  statusButtons: {
    display: 'flex',
    gap: '6px',
  },
  statusBtn: {
    padding: '4px 10px',
    borderRadius: '4px',
    border: 'none',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'pointer',
    textTransform: 'capitalize',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '60px 20px',
    gap: '16px',
  },
  scoreCard: {
    padding: '24px',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    marginBottom: '20px',
  },
  scoreHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  bigScore: {
    textAlign: 'center',
  },
  countsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '12px',
    marginBottom: '20px',
  },
  countCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '16px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
  },
  recommendationBox: {
    padding: '16px',
    borderRadius: '8px',
    border: '2px solid',
    marginBottom: '20px',
  },
  reportBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '12px 24px',
    background: '#22c55e',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
};
