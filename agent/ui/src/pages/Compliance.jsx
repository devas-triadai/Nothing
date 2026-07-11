import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  ShieldCheck, FileText, Upload, CheckCircle, XCircle, AlertTriangle,
  ChevronDown, ChevronUp, Download, Play, Loader2, ArrowLeft,
  Check, AlertCircle, Minus, ChevronRight, ChevronLeft,
  FileCheck, BarChart3, List, PieChart, BookOpen, HardDrive, Database,
  Archive, FolderOpen, File
} from 'lucide-react';
import { getToken, getUser, getDashboardUrl } from '../utils/auth';
import api, { backendApi } from '../utils/api';
import { useTheme } from '../utils/ThemeContext';

// ── Verdict Color Map ──
const VERDICT_STYLES = {
  COMPLIANT: { bg: 'rgba(34, 197, 94, 0.15)', text: '#22c55e', icon: CheckCircle },
  PARTIAL: { bg: 'rgba(234, 179, 8, 0.15)', text: '#eab308', icon: AlertTriangle },
  NON_COMPLIANT: { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', icon: XCircle },
  UNVERIFIABLE: { bg: 'rgba(156, 163, 175, 0.15)', text: '#9ca3af', icon: Minus },
};

// ── Status Badge ──
function StatusBadge({ status, confidence }) {
  const style = VERDICT_STYLES[status] || { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', icon: Loader2 };
  const Icon = style.icon;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '4px 10px', borderRadius: '20px', background: style.bg, color: style.text,
      fontSize: '12px', fontWeight: 600, textTransform: 'capitalize'
    }}>
      <Icon size={12} />
      {status ? status.replace(/_/g, '-').toLowerCase() : 'pending'}
      {confidence !== undefined && <span style={{ opacity: 0.8, marginLeft: '4px' }}>{(confidence * 100).toFixed(0)}%</span>}
    </span>
  );
}

// ── Progress Bar ──
function ProgressBar({ percent, color = '#22c55e' }) {
  return (
    <div style={{ width: '100%', height: '8px', background: 'var(--border, #e2e8f0)', borderRadius: '4px', overflow: 'hidden' }}>
      <div style={{ width: `${percent}%`, height: '100%', background: color, borderRadius: '4px', transition: 'width 0.3s ease' }} />
    </div>
  );
}

// ── File Upload Slot ──
function FileSlot({ label, required, file, onChange, isDark, accept }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <label style={{ fontSize: '13px', fontWeight: 500, color: isDark ? '#cbd5e1' : '#475569' }}>
        {label} {required && <span style={{ color: '#ef4444' }}>*</span>}
      </label>
      <div style={{
        padding: '12px', border: `2px dashed ${file ? '#4a8bff' : (isDark ? '#334155' : '#e2e8f0')}`,
        borderRadius: '8px', background: file ? 'rgba(74,139,255,0.06)' : 'transparent',
        transition: 'all 0.15s'
      }}>
        <input
          type="file"
          accept={accept || '.pdf,.doc,.docx,.txt,.xlsx,.pptx,.png,.jpg,.jpeg'}
          onChange={(e) => onChange(e.target.files?.[0] || null)}
          style={{ fontSize: '12px', width: '100%' }}
        />
        {file && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px', padding: '6px 10px', background: 'rgba(74,139,255,0.1)', borderRadius: '6px' }}>
            <FileText size={16} color="#4a8bff" />
            <span style={{ fontSize: '12px', color: isDark ? '#e2e8f0' : '#1e293b', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
            <button onClick={() => onChange(null)} style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '16px', padding: 0 }}>×</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── ZIP Upload Slot ──
function ZipFileSlot({ label, required, file, onChange, isDark }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <label style={{ fontSize: '13px', fontWeight: 500, color: isDark ? '#cbd5e1' : '#475569' }}>
        {label} {required && <span style={{ color: '#ef4444' }}>*</span>}
      </label>
      <div style={{
        padding: '12px', border: `2px dashed ${file ? '#8b5cf6' : (isDark ? '#334155' : '#e2e8f0')}`,
        borderRadius: '8px', background: file ? 'rgba(139,92,246,0.06)' : 'transparent',
        transition: 'all 0.15s'
      }}>
        <input
          type="file"
          accept=".zip"
          onChange={(e) => onChange(e.target.files?.[0] || null)}
          style={{ fontSize: '12px', width: '100%' }}
        />
        {file && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px', padding: '6px 10px', background: 'rgba(139,92,246,0.1)', borderRadius: '6px' }}>
            <Archive size={16} color="#8b5cf6" />
            <span style={{ fontSize: '12px', color: isDark ? '#e2e8f0' : '#1e293b', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
            <button onClick={() => onChange(null)} style={{ background: 'transparent', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '16px', padding: 0 }}>×</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── ZIP File Preview ──
function ZipFilePreview({ files, onToggle, onSelectAll, onDeselectAll, isDark }) {
  if (!files || files.length === 0) return null;

  const selectedCount = files.filter(f => f.selected).length;

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileIcon = (filename) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (['pdf'].includes(ext)) return <FileText size={14} color="#ef4444" />;
    if (['doc', 'docx'].includes(ext)) return <FileText size={14} color="#3b82f6" />;
    if (['xls', 'xlsx', 'csv'].includes(ext)) return <FileText size={14} color="#22c55e" />;
    if (['ppt', 'pptx'].includes(ext)) return <FileText size={14} color="#f97316" />;
    return <File size={14} color={isDark ? '#94a3b8' : '#64748b'} />;
  };

  return (
    <div style={{
      marginTop: '12px', padding: '12px', borderRadius: '8px',
      background: isDark ? '#1e293b' : '#f8fafc',
      border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FolderOpen size={16} color="#8b5cf6" />
          <span style={{ fontSize: '13px', fontWeight: 600, color: isDark ? '#e2e8f0' : '#1e293b' }}>
            Extracted Files ({selectedCount} of {files.length} selected)
          </span>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button onClick={onSelectAll} style={{
            padding: '3px 8px', borderRadius: '4px', border: `1px solid ${isDark ? '#475569' : '#d1d5db'}`,
            background: 'transparent', color: isDark ? '#94a3b8' : '#64748b',
            fontSize: '10px', fontWeight: 500, cursor: 'pointer'
          }}>Select All</button>
          <button onClick={onDeselectAll} style={{
            padding: '3px 8px', borderRadius: '4px', border: `1px solid ${isDark ? '#475569' : '#d1d5db'}`,
            background: 'transparent', color: isDark ? '#94a3b8' : '#64748b',
            fontSize: '10px', fontWeight: 500, cursor: 'pointer'
          }}>Deselect All</button>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '200px', overflowY: 'auto' }}>
        {files.map((f, idx) => (
          <div key={idx} onClick={() => onToggle(idx)} style={{
            display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px',
            borderRadius: '6px', cursor: 'pointer', transition: 'background 0.1s',
            background: f.selected ? 'rgba(139,92,246,0.08)' : 'transparent',
            border: `1px solid ${f.selected ? 'rgba(139,92,246,0.2)' : 'transparent'}`
          }}>
            <div style={{
              width: '16px', height: '16px', borderRadius: '3px',
              border: `2px solid ${f.selected ? '#8b5cf6' : (isDark ? '#475569' : '#d1d5db')}`,
              background: f.selected ? '#8b5cf6' : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.1s'
            }}>
              {f.selected && <Check size={10} color="#fff" />}
            </div>
            {getFileIcon(f.filename)}
            <span style={{
              fontSize: '12px', flex: 1,
              color: f.selected ? (isDark ? '#e2e8f0' : '#1e293b') : (isDark ? '#64748b' : '#94a3b8')
            }}>{f.filename}</span>
            <span style={{ fontSize: '10px', color: isDark ? '#64748b' : '#94a3b8' }}>
              {formatSize(f.size)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Page ──
export default function Compliance() {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const [activeTab, setActiveTab] = useState('setup');
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [standards, setStandards] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [expandedClauses, setExpandedClauses] = useState({});
  const [polling, setPolling] = useState(false);

  // Form state
  const [refName, setRefName] = useState('');
  const [sotrCom, setSotrCom] = useState(null);
  const [sotrTech, setSotrTech] = useState(null);
  const [vendorCom, setVendorCom] = useState(null);
  const [vendorComFiles, setVendorComFiles] = useState([]);
  const [vendorDpr, setVendorDpr] = useState(null);
  const [selectedStandards, setSelectedStandards] = useState([]);
  const [standardRelevance, setStandardRelevance] = useState([]);
  const [runProgress, setRunProgress] = useState(null);

  const pollRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => { mountedRef.current = false; };
  }, []);

  const toggleClauseExpand = (id) => {
    setExpandedClauses(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // ── Auth ──
  useEffect(() => {
    const token = getToken();
    if (!token) { navigate('/'); return; }
    const user = getUser();
    if (user?.role === 'super_admin' || user?.is_superadmin) setIsSuperAdmin(true);
  }, [navigate]);

  // ── Fetch Data ──
  const fetchRuns = useCallback(async () => {
    try {
      const res = await backendApi.get('/compliance/runs?limit=20');
      if (mountedRef.current) setRuns(res.data || []);
    } catch (err) { console.error('Failed to fetch runs:', err); }
  }, []);

  const fetchStandards = useCallback(async () => {
    try {
      const res = await api.get('/compliance/standards');
      if (mountedRef.current) setStandards(res.data || []);
    } catch (err) {
      console.error('Failed to fetch standards:', err);
      if (mountedRef.current) setStandards([]);
    }
  }, []);

  // ── Fetch Standards Relevance ──
  const relevanceTimerRef = useRef(null);

  const fetchRelevance = useCallback(async (comFile, techFile) => {
    if (!comFile && !techFile) {
      setStandardRelevance([]);
      return;
    }
    try {
      const formData = new FormData();
      if (comFile) formData.append('sotr_commercial', comFile);
      if (techFile) formData.append('sotr_technical', techFile);
      const res = await backendApi.post('/compliance/standards/relevance', formData, { timeout: 60000 });
      if (!mountedRef.current) return;
      const rel = res.data || [];
      setStandardRelevance(rel);
      // Auto-select recommended standards
      const recommendedIds = rel.filter(r => r.recommended).map(r => r.doc_id);
      if (recommendedIds.length > 0) {
        setSelectedStandards(prev => [...new Set([...prev, ...recommendedIds])]);
      }
    } catch (err) {
      console.error('Failed to fetch relevance:', err);
    }
  }, []);

  useEffect(() => {
    if (relevanceTimerRef.current) clearTimeout(relevanceTimerRef.current);
    relevanceTimerRef.current = setTimeout(() => {
      fetchRelevance(sotrCom, sotrTech);
    }, 800);
    return () => { if (relevanceTimerRef.current) clearTimeout(relevanceTimerRef.current); };
  }, [sotrCom, sotrTech, fetchRelevance]);

  useEffect(() => {
    fetchRuns();
    fetchStandards();
  }, [fetchRuns, fetchStandards]);

  // ── Poll Status ──
  const pollStatus = useCallback(async (runId) => {
    if (pollRef.current) clearTimeout(pollRef.current); // cancel previous poll
    const check = async () => {
      if (!mountedRef.current) return;
      try {
        const res = await backendApi.get(`/compliance/runs/${runId}/status`);
        if (!mountedRef.current) return;
        setRunProgress(res.data);
          if (res.data.status === 'complete' || res.data.status === 'failed') {
            setPolling(false);
            if (res.data.status === 'complete') {
              const detail = await backendApi.get(`/compliance/runs/${runId}?include_clauses=true`);
              if (mountedRef.current) {
                setRunDetails(detail.data);
                setSelectedRun(detail.data);
                setActiveTab('results');
                if (detail.data.vendor_commercial_files) {
                  setVendorComFiles(detail.data.vendor_commercial_files);
                } else {
                  fetchZipContents(runId);
                }
              }
            }
          fetchRuns();
          return;
        }
        pollRef.current = setTimeout(check, 2000);
      } catch (err) {
        console.error('Poll error:', err);
        if (mountedRef.current) setPolling(false);
      }
    };
    setPolling(true);
    check();
  }, [fetchRuns]);

  useEffect(() => {
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  // ── Create Run ──
  const handleCreateRun = async () => {
    const missing = [];
    if (!refName.trim()) missing.push('Reference Name');
    const pair1 = sotrCom && vendorCom;
    const pair2 = sotrTech && vendorDpr;
    if (!pair1 && !pair2) {
      if ((sotrCom && !vendorCom) || (!sotrCom && vendorCom) || (sotrTech && !vendorDpr) || (!sotrTech && vendorDpr)) {
        missing.push('SOTR & Vendor files must be paired together (Commercial pair or Technical/DPR pair)');
      } else {
        missing.push('Upload SOTR Commercial + Vendor Commercial, or SOTR Technical + Vendor DPR, or all 4 files');
      }
    }
    if (missing.length > 0) {
      setError(`Missing required fields: ${missing.join(', ')}`);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('reference_name', refName.trim());
      if (sotrCom) formData.append('sotr_commercial', sotrCom);
      if (sotrTech) formData.append('sotr_technical', sotrTech);
      if (vendorCom) formData.append('vendor_commercial', vendorCom);
      if (vendorDpr) formData.append('vendor_dpr', vendorDpr);
      formData.append('selected_standards', JSON.stringify(selectedStandards));

      const res = await backendApi.post('/compliance/runs', formData, {
        timeout: 300000,
      });

      setSelectedRun(res.data);
      setRunDetails(null);
      setActiveTab('progress');
      pollStatus(res.data.id);
      fetchRuns();
      if (vendorCom) fetchZipContents(res.data.id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail) ? detail.map(d => d.msg || String(d)).join('; ') : (detail || err.message || 'Failed to create compliance run');
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Toggle Standard ──
  const toggleStandard = (docId) => {
    setSelectedStandards(prev =>
      prev.includes(docId) ? prev.filter(id => id !== docId) : [...prev, docId]
    );
  };

  // ── ZIP File Handlers ──
  const handleVendorComChange = (file) => {
    setVendorCom(file);
    setVendorComFiles([]);
  };

  const handleToggleVendorFile = async (idx) => {
    const file = vendorComFiles[idx];
    if (!file || !runDetails?.id) return;
    try {
      await backendApi.patch(`/compliance/runs/${runDetails.id}/toggle-file`, {
        filename: file.filename,
        selected: !file.selected
      });
      setVendorComFiles(prev => prev.map((f, i) => i === idx ? { ...f, selected: !f.selected } : f));
    } catch (err) {
      console.error('Failed to toggle file:', err);
      setError('Failed to toggle file selection');
    }
  };

  const handleSelectAllVendorFiles = async () => {
    if (!runDetails?.id) return;
    try {
      await Promise.all(vendorComFiles.filter(f => !f.selected).map(f =>
        backendApi.patch(`/compliance/runs/${runDetails.id}/toggle-file`, { filename: f.filename, selected: true })
      ));
      setVendorComFiles(prev => prev.map(f => ({ ...f, selected: true })));
    } catch (err) {
      console.error('Failed to select all files:', err);
    }
  };

  const handleDeselectAllVendorFiles = async () => {
    if (!runDetails?.id) return;
    const selectedFiles = vendorComFiles.filter(f => f.selected);
    if (selectedFiles.length <= 1) return; // Keep at least 1 selected
    try {
      await Promise.all(selectedFiles.slice(0, -1).map(f =>
        backendApi.patch(`/compliance/runs/${runDetails.id}/toggle-file`, { filename: f.filename, selected: false })
      ));
      setVendorComFiles(prev => prev.map((f, i) => {
        const lastSelectedIdx = prev.findIndex(x => x.selected);
        return { ...f, selected: prev.indexOf(f) === lastSelectedIdx };
      }));
    } catch (err) {
      console.error('Failed to deselect all files:', err);
    }
  };

  const fetchZipContents = useCallback(async (runId) => {
    try {
      const res = await backendApi.get(`/compliance/runs/${runId}/zip-contents`);
      if (mountedRef.current && res.data?.files) {
        setVendorComFiles(res.data.files);
      }
    } catch (err) {
      console.error('Failed to fetch ZIP contents:', err);
    }
  }, []);

  const canStart = refName.trim() && ((sotrCom && vendorCom) || (sotrTech && vendorDpr));

  // ── Render ──
  const S = styles;
  const bg = isDark ? '#0f172a' : '#f1f5f9';

  return (
    <div style={{ ...S.layout, background: bg }}>
      {/* ── Sidebar ── */}
      <aside style={{ ...S.sidebar, width: sidebarCollapsed ? '60px' : '260px', background: isDark ? '#1e293b' : '#fff', borderColor: isDark ? '#334155' : '#e2e8f0' }}>
        <div style={{ ...S.sideHeader, flexDirection: sidebarCollapsed ? 'column' : 'row', borderColor: isDark ? '#334155' : '#e2e8f0' }}>
          <div style={S.logoGroup}>
            <div style={S.logoIcon}><ShieldCheck size={20} color="#4a8bff" /></div>
            {!sidebarCollapsed && <div><div style={{ ...S.logoText, color: isDark ? '#fff' : '#1e293b' }}>AGRA</div><div style={S.logoSub}>Compliance</div></div>}
          </div>
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} style={S.collapseBtn}>{sidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}</button>
        </div>

        <div style={S.navSection}>
          <Link to="/" style={{ ...S.navLink, color: isDark ? '#94a3b8' : '#64748b' }}><ArrowLeft size={15} />{!sidebarCollapsed && <span>Back to Chat</span>}</Link>
          {isSuperAdmin && (
            <a href={getDashboardUrl('/dashboard')} style={{ ...S.navLink, color: isDark ? '#94a3b8' : '#64748b' }}>
              <BarChart3 size={15} />{!sidebarCollapsed && <span>Dashboard</span>}
            </a>
          )}
        </div>

        {!sidebarCollapsed && runs.length > 0 && (
          <div style={S.section}>
            <div style={{ ...S.sectionTitle, color: isDark ? '#64748b' : '#94a3b8' }}>Recent Runs</div>
            {runs.slice(0, 5).map(r => (
              <div key={r.id} onClick={() => { setSelectedRun(r); setActiveTab('results'); backendApi.get(`/compliance/runs/${r.id}?include_clauses=true`).then(res => { setRunDetails(res.data); if (res.data.vendor_commercial_files) { setVendorComFiles(res.data.vendor_commercial_files); } else { fetchZipContents(r.id); } }).catch(() => {}); }}
                style={{ ...S.evalItem, background: selectedRun?.id === r.id ? (isDark ? '#334155' : '#e2e8f0') : 'transparent' }}>
                <FileText size={14} color={isDark ? '#94a3b8' : '#64748b'} />
                <div style={S.evalInfo}>
                  <div style={{ fontSize: '11px', color: isDark ? '#e2e8f0' : '#1e293b', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.reference_name || `Run #${r.id}`}</div>
                  <StatusBadge status={r.status} />
                </div>
              </div>
            ))}
          </div>
        )}
      </aside>

      {/* ── Main Content ── */}
      <main style={{ ...S.main, background: bg }}>
        <header style={{ ...S.header, background: isDark ? '#1e293b' : '#fff', borderColor: isDark ? '#334155' : '#e2e8f0' }}>
          <div style={S.headerTitle}>
            <FileCheck size={24} color="#4a8bff" />
            <div>
              <h1 style={{ ...S.title, color: isDark ? '#fff' : '#1e293b' }}>Compliance Verification</h1>
              <p style={{ ...S.subtitle, color: isDark ? '#94a3b8' : '#64748b' }}>SOTR vs Vendor Submission Analysis</p>
            </div>
          </div>
          <div style={S.tabs}>
            {['setup', 'progress', 'results'].map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                style={{ ...S.tab, color: activeTab === tab ? '#4a8bff' : (isDark ? '#94a3b8' : '#64748b'), borderBottomColor: activeTab === tab ? '#4a8bff' : 'transparent' }}>
                {tab === 'setup' && <Upload size={16} />}
                {tab === 'progress' && <Loader2 size={16} />}
                {tab === 'results' && <List size={16} />}
                <span style={{ textTransform: 'capitalize' }}>{tab}</span>
              </button>
            ))}
          </div>
        </header>

        <div style={S.content}>
          {error && (
            <div style={S.errorAlert}>
              <AlertCircle size={18} />
              {error}
              <button onClick={() => setError(null)} style={S.closeBtn}>×</button>
            </div>
          )}

          {/* ── SETUP TAB ── */}
          {activeTab === 'setup' && (
            <div style={S.panel}>
              <h2 style={{ ...S.panelTitle, color: isDark ? '#fff' : '#1e293b' }}>New Compliance Run</h2>

              <div style={{ marginBottom: '24px' }}>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: isDark ? '#e2e8f0' : '#334155', margin: '0 0 12px' }}>
                  Stage 1: SOTR Documents (Commercial paired with Vendor Commercial, Technical paired with Vendor DPR)
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '16px' }}>
                  <label style={{ fontSize: '13px', fontWeight: 500, color: isDark ? '#cbd5e1' : '#475569' }}>
                    Reference Name <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <input type="text" value={refName}
                    onChange={(e) => setRefName(e.target.value)}
                    placeholder="e.g., OPV Construction - ABC Shipyard"
                    style={{ padding: '10px 12px', borderRadius: '8px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`, background: isDark ? '#334155' : '#fff', color: isDark ? '#fff' : '#1e293b', fontSize: '14px', outline: 'none' }}
                  />
                  {!refName.trim() && <span style={{ fontSize: '11px', color: '#eab308' }}>Required: enter a reference name for this compliance run</span>}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                  <FileSlot label="SOTR Commercial" required file={sotrCom} onChange={setSotrCom} isDark={isDark} />
                  <FileSlot label="SOTR Technical" file={sotrTech} onChange={setSotrTech} isDark={isDark} />
                </div>
              </div>

              <div style={{ marginBottom: '24px' }}>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: isDark ? '#e2e8f0' : '#334155', margin: '0 0 12px' }}>
                  Stage 2: Vendor Submission Documents
                </h3>
                <p style={{ fontSize: '11px', color: isDark ? '#94a3b8' : '#64748b', margin: '-8px 0 12px' }}>
                  SOTR Commercial requires Vendor Commercial ZIP; SOTR Technical requires Vendor DPR. 2 files (one pair) or all 4 files.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', alignItems: 'start' }}>
                  <div>
                    <ZipFileSlot label="Vendor Commercial (ZIP)" file={vendorCom} onChange={handleVendorComChange} isDark={isDark} />
                    <ZipFilePreview
                      files={vendorComFiles}
                      onToggle={handleToggleVendorFile}
                      onSelectAll={handleSelectAllVendorFiles}
                      onDeselectAll={handleDeselectAllVendorFiles}
                      isDark={isDark}
                    />
                  </div>
                  <FileSlot label="Vendor DPR / Technical Response" file={vendorDpr} onChange={setVendorDpr} isDark={isDark} />
                </div>
              </div>

              {/* ── Standards Selector ── */}
              <div style={{ marginBottom: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h3 style={{ fontSize: '15px', fontWeight: 600, color: isDark ? '#e2e8f0' : '#334155', margin: 0 }}>
                    House Rules / Standards
                  </h3>
                  {standards.length > 0 && (
                    <div style={{ display: 'flex', gap: '4px' }}>
                      <button onClick={() => setSelectedStandards(standards.map(s => s.doc_id))} style={{
                        padding: '3px 8px', borderRadius: '4px', border: `1px solid ${isDark ? '#475569' : '#d1d5db'}`,
                        background: 'transparent', color: isDark ? '#94a3b8' : '#64748b',
                        fontSize: '10px', fontWeight: 500, cursor: 'pointer'
                      }}>Select All</button>
                      <button onClick={() => setSelectedStandards([])} style={{
                        padding: '3px 8px', borderRadius: '4px', border: `1px solid ${isDark ? '#475569' : '#d1d5db'}`,
                        background: 'transparent', color: isDark ? '#94a3b8' : '#64748b',
                        fontSize: '10px', fontWeight: 500, cursor: 'pointer'
                      }}>Deselect All</button>
                    </div>
                  )}
                </div>
                <p style={{ fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b', margin: '0 0 8px' }}>
                  Select standards to check against. Relevant standards are auto-selected when you upload SOTR documents.
                </p>
                {standardRelevance.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 10px', background: 'rgba(34,197,94,0.06)', borderRadius: '6px', marginBottom: '8px', border: '1px solid rgba(34,197,94,0.15)' }}>
                    <CheckCircle size={13} color="#22c55e" />
                    <span style={{ fontSize: '11px', color: '#22c55e', fontWeight: 500 }}>
                      {standardRelevance.filter(r => r.recommended).length} of {standards.length} standards auto-selected based on content analysis
                    </span>
                  </div>
                )}
                {standards.length === 0 ? (
                  <p style={{ fontSize: '12px', color: '#eab308' }}>No standards documents found in knowledge base.</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '260px', overflowY: 'auto', padding: '6px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`, borderRadius: '8px', background: isDark ? '#0f172a' : '#fafbfc' }}>
                    {(() => {
                      const getCat = (fname) => {
                        const f = (fname || '').replace(/\.txt$/i, '');
                        if (/^ICG_/i.test(f) || f.includes('ICG')) return 'ICG';
                        if (/^IMO_/i.test(f) || f.includes('IMO') || f.includes('SOLAS') || f.includes('MARPOL') || f.includes('STCW')) return 'IMO';
                        if (/^SAMPLE_/i.test(f)) return 'SAMPLE';
                        return 'Other';
                      };
                      const catOrder = { ICG: 0, IMO: 1, SAMPLE: 2, Other: 3 };
                      const sorted = [...standards].sort((a, b) => {
                        const catA = catOrder[getCat(a.filename)] ?? 3;
                        const catB = catOrder[getCat(b.filename)] ?? 3;
                        if (catA !== catB) return catA - catB;
                        const relA = standardRelevance.find(r => r.doc_id === a.doc_id);
                        const relB = standardRelevance.find(r => r.doc_id === b.doc_id);
                        return (relB?.score || 0) - (relA?.score || 0);
                      });
                      let lastSection = null;
                      return sorted.map(s => {
                        const selected = selectedStandards.includes(s.doc_id);
                        const rel = standardRelevance.find(r => r.doc_id === s.doc_id);
                        const isRecommended = rel?.recommended;
                        const fname = (s.filename || s.doc_id).replace(/\.txt$/i, '');
                        const category = getCat(s.filename);
                        const showDivider = category !== lastSection;
                        lastSection = category;
                        return (
                          <React.Fragment key={s.doc_id}>
                            {showDivider && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 8px', marginTop: '2px' }}>
                                <span style={{ fontSize: '9px', fontWeight: 700, color: isDark ? '#64748b' : '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{category}</span>
                                <div style={{ flex: 1, height: '1px', background: isDark ? '#1e293b' : '#e2e8f0' }} />
                              </div>
                            )}
                            <div onClick={() => toggleStandard(s.doc_id)}
                              title={rel?.reasons?.length ? `Relevance: ${rel.reasons.join('; ')}` : ''}
                              style={{
                                display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 10px',
                                borderRadius: '6px', cursor: 'pointer', transition: 'all 0.12s',
                                border: `1px solid ${selected ? '#4a8bff' : 'transparent'}`,
                                background: selected ? 'rgba(74,139,255,0.08)' : isRecommended ? 'rgba(34,197,94,0.04)' : 'transparent',
                              }}
                              onMouseEnter={(e) => { if (!selected) e.currentTarget.style.background = isDark ? '#1e293b' : '#f1f5f9'; }}
                              onMouseLeave={(e) => { if (!selected) e.currentTarget.style.background = isRecommended ? 'rgba(34,197,94,0.04)' : 'transparent'; }}
                            >
                              <div style={{
                                width: '16px', height: '16px', borderRadius: '3px',
                                border: `2px solid ${selected ? '#4a8bff' : (isDark ? '#475569' : '#d1d5db')}`,
                                background: selected ? '#4a8bff' : 'transparent',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                flexShrink: 0, transition: 'all 0.1s'
                              }}>
                                {selected && <Check size={10} color="#fff" />}
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{
                                  fontSize: '12px', color: isDark ? '#e2e8f0' : '#1e293b',
                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                                }}>
                                  {fname}
                                </div>
                                {s.description && (
                                  <div style={{
                                    fontSize: '10px', color: isDark ? '#64748b' : '#94a3b8',
                                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '1px'
                                  }}>
                                    {s.description}
                                  </div>
                                )}
                              </div>
                              {isRecommended && (
                                <span style={{
                                  fontSize: '9px', fontWeight: 700, padding: '2px 7px', borderRadius: '10px',
                                  background: 'rgba(34,197,94,0.12)', color: '#22c55e',
                                  textTransform: 'uppercase', letterSpacing: '0.3px', flexShrink: 0
                                }}>
                                  Recommended
                                </span>
                              )}
                              {rel && rel.score > 0 && (
                                <div style={{
                                  width: '32px', height: '4px', borderRadius: '2px', flexShrink: 0,
                                  background: isDark ? '#1e293b' : '#e2e8f0', overflow: 'hidden'
                                }}>
                                  <div style={{
                                    height: '100%', borderRadius: '2px',
                                    width: `${Math.min(rel.score, 100)}%`,
                                    background: rel.score >= 50 ? '#22c55e' : rel.score >= 25 ? '#eab308' : '#94a3b8'
                                  }} />
                                </div>
                              )}
                            </div>
                          </React.Fragment>
                        );
                      });
                    })()}
                  </div>
                )}
              </div>

              {/* ── Validation Summary ── */}
              <div style={{ marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '4px', padding: '10px 14px', background: isDark ? '#1e293b' : '#f8fafc', borderRadius: '8px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}` }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: isDark ? '#94a3b8' : '#64748b' }}>Required Checklist:</span>
                {[
                  { label: 'Reference Name', ok: !!refName.trim() },
                  { label: 'Commercial Pair (SOTR + Vendor)', ok: !!(sotrCom && vendorCom) },
                  { label: 'Technical Pair (SOTR + Vendor DPR)', ok: !!(sotrTech && vendorDpr) },
                  { label: 'At least one pair complete', ok: !!((sotrCom && vendorCom) || (sotrTech && vendorDpr)) },
                ].map(item => (
                  <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: item.ok ? '#22c55e' : '#ef4444' }}>
                    {item.ok ? <CheckCircle size={11} /> : <XCircle size={11} />}
                    {item.label}
                  </div>
                ))}
              </div>

              <button onClick={handleCreateRun} disabled={!canStart || isLoading}
                style={{
                  opacity: (!canStart || isLoading) ? 0.5 : 1,
                  cursor: (!canStart || isLoading) ? 'not-allowed' : 'pointer',
                  background: '#4a8bff', color: '#fff', border: 'none',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  padding: '12px 24px', borderRadius: '8px', fontSize: '14px', fontWeight: 600, width: '100%'
                }}>
                {isLoading ? <Loader2 size={18} className="spin" /> : <Play size={18} />}
                {isLoading ? 'Creating & Starting...' : 'Start Compliance'}
              </button>
            </div>
          )}

          {/* ── PROGRESS TAB ── */}
          {activeTab === 'progress' && (
            <div style={S.panel}>
              <h2 style={{ ...S.panelTitle, color: isDark ? '#fff' : '#1e293b' }}>Run Progress</h2>
              {selectedRun && (
                <div style={{ padding: '16px', background: isDark ? '#1e293b' : '#fff', borderRadius: '8px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`, marginBottom: '16px' }}>
                  <p style={{ fontSize: '13px', color: isDark ? '#94a3b8' : '#64748b', margin: '0 0 4px' }}>
                    Reference: <strong style={{ color: isDark ? '#e2e8f0' : '#1e293b' }}>{selectedRun.reference_name}</strong>
                  </p>
                  <p style={{ fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b', margin: '0 0 8px' }}>
                    Run #{selectedRun.id}
                  </p>
                </div>
              )}
              {runProgress && (
                <div style={{ padding: '24px', background: isDark ? '#1e293b' : '#fff', borderRadius: '12px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`, textAlign: 'center' }}>
                  <Loader2 size={32} color="#4a8bff" className="spin" style={{ marginBottom: '12px' }} />
                  <p style={{ fontSize: '16px', fontWeight: 600, color: isDark ? '#e2e8f0' : '#1e293b', margin: '0 0 4px' }}>
                    {runProgress.progress?.message || runProgress.status}
                  </p>
                  <p style={{ fontSize: '13px', color: isDark ? '#94a3b8' : '#64748b', margin: '0 0 16px', textTransform: 'capitalize' }}>
                    Stage: {runProgress.status.replace(/_/g, ' ')}
                  </p>
                  <ProgressBar percent={runProgress.progress?.total > 0 ? (runProgress.progress.current / runProgress.progress.total * 100) : 50} color="#4a8bff" />
                  {runProgress.progress?.total > 0 && (
                    <p style={{ fontSize: '11px', color: isDark ? '#64748b' : '#94a3b8', marginTop: '8px' }}>
                      {runProgress.progress.current} / {runProgress.progress.total}
                    </p>
                  )}
                </div>
              )}
              {polling && (
                <p style={{ fontSize: '12px', color: isDark ? '#64748b' : '#94a3b8', textAlign: 'center', marginTop: '12px' }}>
                  Auto-refreshing every 2 seconds...
                </p>
              )}
            </div>
          )}

          {/* ── RESULTS TAB ── */}
          {activeTab === 'results' && (
            <div style={S.panel}>
              {runDetails && runDetails.status === 'complete' ? (
                <>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                    <div>
                      <h2 style={{ ...S.panelTitle, color: isDark ? '#fff' : '#1e293b', margin: 0 }}>
                        {runDetails.reference_name}
                      </h2>
                      <p style={{ fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b', margin: '4px 0 0' }}>
                        Run #{runDetails.id} · {runDetails.total_clauses ?? 0} clauses
                      </p>
                    </div>
                    <button onClick={() => {
                      backendApi.get(`/compliance/runs/${runDetails.id}/report`, { responseType: 'blob' }).then(res => {
                        const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `${runDetails.reference_name.replace(/[\\/:*?"<>|]/g, '_')}_Compliance_Report.docx`;
                        a.click();
                        setTimeout(() => URL.revokeObjectURL(url), 1000);
                      }).catch(err => {
                        console.error('Report download failed:', err);
                        setError(err.response?.data?.detail || err.message || 'Report not ready yet');
                      });
                    }} style={{ ...S.actionBtn, background: '#22c55e' }}>
                      <Download size={16} />
                      Download .docx Report
                    </button>
                  </div>

                  {/* Score Card */}
                  <div style={{ padding: '20px', background: isDark ? '#1e293b' : '#fff', borderRadius: '12px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`, marginBottom: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <div>
                        <h3 style={{ margin: 0, fontSize: '16px', color: isDark ? '#e2e8f0' : '#1e293b' }}>Overall Score</h3>
                        <p style={{ margin: '2px 0 0', fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b' }}>
                          {runDetails.total_clauses} clauses evaluated
                        </p>
                      </div>
                      <span style={{ fontSize: '42px', fontWeight: 700, color: runDetails.overall_score >= 80 ? '#22c55e' : runDetails.overall_score >= 60 ? '#eab308' : '#ef4444' }}>
                        {runDetails.overall_score?.toFixed(0)}%
                      </span>
                    </div>
                    <ProgressBar percent={runDetails.overall_score || 0}
                      color={runDetails.overall_score >= 80 ? '#22c55e' : runDetails.overall_score >= 60 ? '#eab308' : '#ef4444'} />
                    <p style={{ marginTop: '8px', fontSize: '13px', fontWeight: 600, color: isDark ? '#94a3b8' : '#64748b' }}>
                      Recommendation: <span style={{ color: runDetails.recommendation === 'APPROVE' ? '#22c55e' : runDetails.recommendation === 'APPROVE WITH CONDITIONS' ? '#eab308' : runDetails.recommendation === 'REVISE AND RESUBMIT' ? '#f97316' : '#ef4444' }}>
                        {runDetails.recommendation || 'N/A'}
                      </span>
                    </p>
                  </div>

                  {/* Counts Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '16px' }}>
                    {[
                      { label: 'COMPLIANT', count: runDetails.compliant_count ?? 0, color: '#22c55e' },
                      { label: 'PARTIAL', count: runDetails.partial_count ?? 0, color: '#eab308' },
                      { label: 'NON-COMPLIANT', count: runDetails.non_compliant_count ?? 0, color: '#ef4444' },
                      { label: 'UNVERIFIABLE', count: runDetails.unverifiable_count ?? 0, color: '#9ca3af' },
                    ].map(item => (
                      <div key={item.label} style={{ textAlign: 'center', padding: '14px', background: isDark ? '#1e293b' : '#fff', borderRadius: '8px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}` }}>
                        <span style={{ fontSize: '28px', fontWeight: 700, color: item.color, display: 'block' }}>{item.count}</span>
                        <span style={{ fontSize: '10px', fontWeight: 600, color: isDark ? '#94a3b8' : '#64748b', textTransform: 'uppercase', letterSpacing: '0.3px' }}>{item.label}</span>
                      </div>
                    ))}
                  </div>

                  {/* Vendor Commercial Files Preview */}
                  {vendorComFiles.length > 0 && (
                    <div style={{ marginBottom: '16px' }}>
                      <h4 style={{ fontSize: '13px', fontWeight: 600, color: isDark ? '#e2e8f0' : '#334155', margin: '0 0 8px' }}>
                        Vendor Commercial Files
                      </h4>
                      <ZipFilePreview
                        files={vendorComFiles}
                        onToggle={handleToggleVendorFile}
                        onSelectAll={handleSelectAllVendorFiles}
                        onDeselectAll={handleDeselectAllVendorFiles}
                        isDark={isDark}
                      />
                    </div>
                  )}

                  {/* Alerts */}
                  {runDetails.missing_clause_count > 0 && (
                    <div style={{ padding: '10px 14px', background: 'rgba(156,163,175,0.12)', borderRadius: '8px', marginBottom: '10px', border: '1px solid rgba(156,163,175,0.3)' }}>
                      <p style={{ margin: 0, fontSize: '12px', color: '#9ca3af', fontWeight: 600 }}>
                        {runDetails.missing_clause_count} clause(s) with no vendor evidence
                      </p>
                    </div>
                  )}
                  {runDetails.contradiction_count > 0 && (
                    <div style={{ padding: '10px 14px', background: 'rgba(234,179,8,0.1)', borderRadius: '8px', marginBottom: '10px', border: '1px solid rgba(234,179,8,0.3)' }}>
                      <p style={{ margin: 0, fontSize: '12px', color: '#eab308', fontWeight: 600 }}>
                        {runDetails.contradiction_count} contradiction(s) detected between vendor files
                      </p>
                    </div>
                  )}
                  {runDetails.house_rule_violation_count > 0 && (
                    <div style={{ padding: '10px 14px', background: 'rgba(239,68,68,0.1)', borderRadius: '8px', marginBottom: '16px', border: '1px solid rgba(239,68,68,0.3)' }}>
                      <p style={{ margin: 0, fontSize: '12px', color: '#ef4444', fontWeight: 600 }}>
                        {runDetails.house_rule_violation_count} house rule violation(s) detected
                      </p>
                    </div>
                  )}

                  {/* Clause List */}
                  {runDetails.clauses?.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {runDetails.clauses.map((clause) => {
                        const vs = VERDICT_STYLES[clause.verdict] || VERDICT_STYLES.UNVERIFIABLE;
                        return (
                          <div key={clause.id} style={{ padding: '14px', background: isDark ? '#1e293b' : '#fff', borderRadius: '8px', border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}` }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontWeight: 600, color: '#4a8bff', fontSize: '13px' }}>{clause.clause_id}</span>
                                <span style={{ fontSize: '11px', color: isDark ? '#64748b' : '#94a3b8' }}>({clause.source_file})</span>
                                {clause.source_file_detail && (
                                  <span style={{ fontSize: '10px', color: '#8b5cf6', background: 'rgba(139,92,246,0.1)', padding: '1px 6px', borderRadius: '4px' }}>
                                    {clause.source_file_detail}
                                  </span>
                                )}
                              </div>
                              <StatusBadge status={clause.verdict} />
                            </div>

                            <p style={{ fontSize: '12px', color: isDark ? '#cbd5e1' : '#475569', margin: '0 0 6px', lineHeight: 1.4 }}>
                              {expandedClauses[clause.id] ? clause.requirement_text : (clause.requirement_text?.length > 120 ? `${clause.requirement_text.substring(0, 120)}...` : clause.requirement_text)}
                            </p>
                            {clause.requirement_text?.length > 120 && (
                              <button onClick={() => toggleClauseExpand(clause.id)} style={{ background: 'transparent', border: 'none', color: '#4a8bff', fontSize: '10px', fontWeight: 600, cursor: 'pointer', padding: 0, marginBottom: '6px' }}>
                                {expandedClauses[clause.id] ? 'Show less' : 'Show full requirement'}
                              </button>
                            )}

                            {/* Finding */}
                            {clause.finding && (
                              <div style={{ padding: '8px 10px', background: isDark ? '#0f172a' : '#f8fafc', borderRadius: '6px', marginBottom: '6px', fontSize: '12px', color: isDark ? '#94a3b8' : '#64748b', lineHeight: 1.4 }}>
                                <span style={{ fontWeight: 600, color: '#4a8bff', fontSize: '10px', display: 'block', marginBottom: '2px' }}>FINDING:</span>
                                {clause.finding}
                              </div>
                            )}

                            {/* Severity + Recommendation */}
                            <div style={{ display: 'flex', gap: '8px', fontSize: '11px' }}>
                              {clause.severity && (
                                <span style={{ padding: '2px 8px', borderRadius: '4px', background: clause.severity === 'Critical' ? 'rgba(239,68,68,0.15)' : clause.severity === 'Major' ? 'rgba(249,115,22,0.15)' : 'rgba(234,179,8,0.15)', color: clause.severity === 'Critical' ? '#ef4444' : clause.severity === 'Major' ? '#f97316' : '#eab308', fontWeight: 600 }}>
                                  {clause.severity}
                                </span>
                              )}
                              {clause.recommendation && (
                                <span style={{ padding: '2px 8px', borderRadius: '4px', background: 'rgba(74,139,255,0.1)', color: '#4a8bff', fontWeight: 500 }}>
                                  {clause.recommendation}
                                </span>
                              )}
                            </div>

                            {/* House Rule Flag */}
                            {clause.house_rule_flag?.violated && (
                              <div style={{ marginTop: '6px', padding: '8px 10px', background: 'rgba(239,68,68,0.08)', borderRadius: '6px', border: '1px solid rgba(239,68,68,0.2)' }}>
                                <span style={{ fontSize: '10px', fontWeight: 700, color: '#ef4444' }}>HOUSE RULE VIOLATION</span>
                                <p style={{ margin: '2px 0 0', fontSize: '11px', color: '#ef4444' }}>
                                  {clause.house_rule_flag.rule_reference && <><strong>{clause.house_rule_flag.rule_reference}</strong>: </>}
                                  {clause.house_rule_flag.note}
                                </p>
                              </div>
                            )}

                            {/* Contradictions */}
                            {clause.contradictions?.length > 0 && (
                              <div style={{ marginTop: '6px', padding: '8px 10px', background: 'rgba(234,179,8,0.08)', borderRadius: '6px', border: '1px solid rgba(234,179,8,0.2)' }}>
                                <span style={{ fontSize: '10px', fontWeight: 700, color: '#eab308' }}>CONTRADICTION</span>
                                {clause.contradictions.map((c, i) => (
                                  <p key={i} style={{ margin: '2px 0 0', fontSize: '11px', color: isDark ? '#94a3b8' : '#64748b' }}>
                                    {c.note}
                                  </p>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '40px', color: isDark ? '#94a3b8' : '#64748b' }}>
                      <FileText size={48} color={isDark ? '#334155' : '#cbd5e1'} />
                      <p>No clause results available.</p>
                    </div>
                  )}
                </>
              ) : (
                <div style={{ textAlign: 'center', padding: '40px', color: isDark ? '#94a3b8' : '#64748b' }}>
                  <PieChart size={48} color={isDark ? '#334155' : '#cbd5e1'} />
                  <p>Select a completed run from the sidebar or create a new one.</p>
                  <button onClick={() => setActiveTab('setup')} style={S.actionBtn}>
                    <Upload size={16} />
                    New Compliance Run
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

const styles = {
  layout: { display: 'flex', height: '100vh', overflow: 'hidden' },
  sidebar: { display: 'flex', flexDirection: 'column', borderRight: '1px solid', transition: 'width 0.2s ease', overflow: 'hidden' },
  sideHeader: { padding: '14px 12px 10px', borderBottom: '1px solid', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  logoGroup: { display: 'flex', alignItems: 'center', gap: '9px' },
  logoIcon: { width: 34, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '9px', background: 'rgba(74,139,255,0.12)', flexShrink: 0 },
  logoText: { fontSize: '15px', fontWeight: 800, letterSpacing: '1.5px' },
  logoSub: { fontSize: '9px', color: '#64748b', fontWeight: 500, letterSpacing: '0.3px' },
  collapseBtn: { background: 'transparent', border: 'none', color: '#64748b', padding: '4px', borderRadius: '6px', cursor: 'pointer', display: 'flex', opacity: 0.7 },
  navSection: { padding: '10px', display: 'flex', flexDirection: 'column', gap: '4px' },
  navLink: { display: 'flex', alignItems: 'center', gap: '9px', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', textDecoration: 'none' },
  section: { padding: '10px', flex: 1, overflowY: 'auto' },
  sectionTitle: { fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', padding: '0 8px 8px' },
  evalItem: { display: 'flex', alignItems: 'center', gap: '8px', padding: '8px', borderRadius: '6px', cursor: 'pointer' },
  evalInfo: { display: 'flex', flexDirection: 'column', gap: '2px', flex: 1, minWidth: 0 },
  main: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  header: { padding: '16px 24px', borderBottom: '1px solid', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  headerTitle: { display: 'flex', alignItems: 'center', gap: '12px' },
  title: { margin: 0, fontSize: '20px', fontWeight: 600 },
  subtitle: { margin: '2px 0 0', fontSize: '13px' },
  tabs: { display: 'flex', gap: '4px' },
  tab: { display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', border: 'none', background: 'transparent', fontSize: '13px', fontWeight: 500, cursor: 'pointer', borderBottom: '2px solid' },
  content: { flex: 1, overflow: 'auto', padding: '24px' },
  panel: { maxWidth: '900px', margin: '0 auto' },
  panelTitle: { margin: '0 0 20px', fontSize: '18px', fontWeight: 600 },
  actionBtn: { display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', color: '#fff', border: 'none', borderRadius: '6px', fontSize: '13px', fontWeight: 500, cursor: 'pointer' },
  errorAlert: { display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 16px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: '8px', marginBottom: '16px', fontSize: '14px' },
  closeBtn: { marginLeft: 'auto', background: 'transparent', border: 'none', color: '#ef4444', fontSize: '18px', cursor: 'pointer' },
};
