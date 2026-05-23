/**
 * AGRA Chat Enhancement Phase 5 — Drawing Drop Zone
 * Drag-and-drop area for engineering drawing uploads in chat.
 */

import { useState, useCallback } from 'react';
import { Upload, FileImage, AlertCircle } from 'lucide-react';

const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf'];
const MAX_SIZE_MB = 20;

export default function DrawingDropZone({ onFilesDrop, disabled = false, isDark = false }) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState(null);

  const validateFile = (file) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return `Invalid file type: ${file.name}. Allowed: PNG, JPG, PDF`;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large: ${file.name}. Max: ${MAX_SIZE_MB}MB`;
    }
    return null;
  };

  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    setError(null);

    if (disabled) return;

    const files = Array.from(e.dataTransfer.files);
    
    // Validate files
    const validFiles = [];
    for (const file of files) {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      validFiles.push(file);
    }

    if (validFiles.length > 0) {
      onFilesDrop(validFiles);
    }
  }, [disabled, onFilesDrop]);

  const handleFileSelect = useCallback((e) => {
    setError(null);
    const files = Array.from(e.target.files);
    
    const validFiles = [];
    for (const file of files) {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      validFiles.push(file);
    }

    if (validFiles.length > 0) {
      onFilesDrop(validFiles);
    }
  }, [onFilesDrop]);

  const styles = {
    container: {
      border: `2px dashed ${isDragging ? '#3b82f6' : isDark ? '#475569' : '#cbd5e1'}`,
      borderRadius: '12px',
      padding: '24px',
      textAlign: 'center',
      background: isDragging 
        ? (isDark ? 'rgba(59, 130, 246, 0.1)' : 'rgba(59, 130, 246, 0.05)')
        : (isDark ? 'rgba(30, 41, 59, 0.5)' : 'rgba(241, 245, 249, 0.8)'),
      transition: 'all 0.2s ease',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.6 : 1,
      animation: isDragging ? 'dropZonePulse 1.5s ease-in-out infinite' : 'none',
    },
    icon: {
      marginBottom: '12px',
      color: isDragging ? '#3b82f6' : (isDark ? '#64748b' : '#94a3b8'),
    },
    text: {
      fontSize: '14px',
      color: isDark ? '#94a3b8' : '#64748b',
      marginBottom: '8px',
    },
    subtext: {
      fontSize: '12px',
      color: isDark ? '#64748b' : '#94a3b8',
    },
    error: {
      marginTop: '12px',
      padding: '8px 12px',
      background: isDark ? 'rgba(239, 68, 68, 0.2)' : 'rgba(239, 68, 68, 0.1)',
      borderRadius: '8px',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      fontSize: '13px',
      color: '#ef4444',
    },
    fileInput: {
      display: 'none',
    }
  };

  return (
    <div
      style={styles.container}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onClick={() => !disabled && document.getElementById('drawing-file-input').click()}
    >
      <input
        id="drawing-file-input"
        type="file"
        accept=".png,.jpg,.jpeg,.pdf"
        multiple
        onChange={handleFileSelect}
        style={styles.fileInput}
        disabled={disabled}
      />
      
      <div style={styles.icon}>
        {isDragging ? <FileImage size={40} /> : <Upload size={40} />}
      </div>
      
      <div style={styles.text}>
        {isDragging ? 'Drop drawing here' : 'Click or drag drawing to upload'}
      </div>
      
      <div style={styles.subtext}>
        PNG, JPG, PDF up to {MAX_SIZE_MB}MB
      </div>

      {error && (
        <div style={styles.error}>
          <AlertCircle size={16} />
          {error}
        </div>
      )}
    </div>
  );
}
