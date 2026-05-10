import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Image as ImageIcon, Upload, Loader2, CheckCircle, Crosshair, ClipboardList, Layers } from 'lucide-react';
import api, { getApiUrl } from '../utils/api';
import { getToken } from '../utils/auth';

export default function DrawingPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState('');
  
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | processing | completed | error
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    if (!file.type.startsWith('image/')) {
      setErrorMsg('Please upload a valid image file (PNG, JPG, etc).');
      return;
    }
    
    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setResult(null);
    setStatus('idle');
    setJobId(null);
    setErrorMsg('');
  };

  const handleExtract = async () => {
    if (!selectedFile) return;
    
    setStatus('processing');
    setErrorMsg('');
    
    const formData = new FormData();
    formData.append('image', selectedFile);
    
    try {
      const token = getToken();
      const res = await fetch(getApiUrl('/api/agent/drawing/extract_parameters'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to submit extraction job');
      
      setJobId(data.job_id);
    } catch (e) {
      setStatus('error');
      setErrorMsg(e.message);
    }
  };

  useEffect(() => {
    let interval;
    if (status === 'processing' && jobId) {
      interval = setInterval(async () => {
        try {
          const { data } = await api.get(`/drawing/jobs/${jobId}`);
          if (data.status === 'completed') {
            setStatus('completed');
            setResult(data.result_data);
            clearInterval(interval);
          } else if (data.status === 'failed') {
            setStatus('error');
            setErrorMsg(data.error_message || 'Job failed on the server.');
            clearInterval(interval);
          }
        } catch (e) {
          console.error("Failed to poll status", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [status, jobId]);

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <button onClick={() => navigate(-1)} style={styles.backBtn}><ArrowLeft size={18} /></button>
        <div>
          <h1 style={styles.title}>Multimodal Drawing Analysis</h1>
          <p style={styles.subtitle}>Upload engineering drawings or schematics for Vision-Language parsing</p>
        </div>
      </div>

      <div style={styles.grid}>
        <div style={styles.card}>
          <h2 style={styles.cardTitle}><ImageIcon size={18} /> Upload Drawing</h2>
          
          <div 
            style={styles.uploadArea} 
            onClick={() => fileInputRef.current?.click()}
          >
            {previewUrl ? (
              <img src={previewUrl} alt="Preview" style={styles.preview} />
            ) : (
              <div style={styles.uploadPlaceholder}>
                <Upload size={32} color="var(--primary)" />
                <span style={{ fontWeight: 600, color: 'var(--text-heading)', marginTop: 12 }}>Click to upload drawing</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>PNG, JPG, BMP up to 10MB</span>
              </div>
            )}
          </div>
          <input 
            type="file" 
            ref={fileInputRef} 
            style={{ display: 'none' }} 
            accept="image/*"
            onChange={handleFileChange}
          />
          
          <div style={{ marginTop: 20 }}>
            <button 
              onClick={handleExtract} 
              disabled={!selectedFile || status === 'processing'}
              style={{...styles.extractBtn, opacity: (!selectedFile || status === 'processing') ? 0.6 : 1}}
            >
              {status === 'processing' ? (
                <><Loader2 size={16} className="animate-spin" /> Processing via VLM...</>
              ) : (
                <><Crosshair size={16} /> Extract Parameters</>
              )}
            </button>
          </div>
          
          {errorMsg && (
            <div style={styles.errorBox}>{errorMsg}</div>
          )}
        </div>

        <div style={styles.card}>
          <h2 style={styles.cardTitle}><ClipboardList size={18} /> Extraction Results</h2>
          
          {status === 'idle' && !result && (
            <div style={styles.emptyState}>
              Upload a drawing and run extraction to see detected parameters, dimensions, and materials.
            </div>
          )}
          
          {status === 'processing' && (
            <div style={styles.emptyState}>
              <Loader2 size={32} color="var(--primary)" className="animate-spin" style={{ marginBottom: 16 }} />
              <div>Running OpenCV preprocessing pipeline (deskew, denoise, binarize)...</div>
              <div style={{ marginTop: 8, fontSize: 12 }}>Passing optimized image to Gemma-4-Vision for parameter extraction</div>
            </div>
          )}
          
          {status === 'completed' && result && (
            <div className="animate-fade-in" style={styles.resultsWrap}>
              <div style={styles.resultGroup}>
                <h3 style={styles.groupTitle}><Layers size={14}/> Dimensions</h3>
                {result.dimensions?.length > 0 ? (
                  <ul style={styles.list}>
                    {result.dimensions.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                ) : <span style={styles.noneText}>None detected</span>}
              </div>
              
              <div style={styles.resultGroup}>
                <h3 style={styles.groupTitle}><Layers size={14}/> Tolerances</h3>
                {result.tolerances?.length > 0 ? (
                  <ul style={styles.list}>
                    {result.tolerances.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                ) : <span style={styles.noneText}>None detected</span>}
              </div>
              
              <div style={styles.resultGroup}>
                <h3 style={styles.groupTitle}><Layers size={14}/> Materials</h3>
                {result.materials?.length > 0 ? (
                  <ul style={styles.list}>
                    {result.materials.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                ) : <span style={styles.noneText}>None detected</span>}
              </div>
              
              <div style={styles.resultGroup}>
                <h3 style={styles.groupTitle}><Layers size={14}/> Equipment Tags</h3>
                {result.equipment_tags?.length > 0 ? (
                  <ul style={styles.list}>
                    {result.equipment_tags.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                ) : <span style={styles.noneText}>None detected</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: { padding: '28px 32px', maxWidth: '1200px', margin: '0 auto', minHeight: '100vh' },
  header: { display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '24px' },
  backBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: 38, height: 38, borderRadius: 'var(--radius-md)', background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-secondary)', cursor: 'pointer' },
  title: { fontSize: '22px', fontWeight: 700, color: 'var(--text-heading)', margin: 0 },
  subtitle: { fontSize: '13px', color: 'var(--text-muted)', margin: 0 },
  grid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' },
  card: { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '24px', display: 'flex', flexDirection: 'column' },
  cardTitle: { display: 'flex', alignItems: 'center', gap: '8px', fontSize: '16px', fontWeight: 600, color: 'var(--text-heading)', margin: '0 0 20px 0', borderBottom: '1px solid var(--border)', paddingBottom: '12px' },
  uploadArea: { border: '2px dashed var(--border)', borderRadius: 'var(--radius-md)', height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', overflow: 'hidden', background: 'var(--bg-surface)' },
  uploadPlaceholder: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  preview: { width: '100%', height: '100%', objectFit: 'contain' },
  extractBtn: { width: '100%', padding: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', background: 'var(--primary)', color: '#fff', border: 'none', borderRadius: 'var(--radius-md)', fontSize: '14px', fontWeight: 600, cursor: 'pointer' },
  emptyState: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', textAlign: 'center', padding: '40px' },
  resultsWrap: { display: 'flex', flexDirection: 'column', gap: '16px' },
  resultGroup: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '16px' },
  groupTitle: { display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 12px 0' },
  list: { margin: 0, paddingLeft: '20px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.6' },
  noneText: { fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic' },
  errorBox: { marginTop: '16px', padding: '12px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: '8px', fontSize: '13px' }
};
