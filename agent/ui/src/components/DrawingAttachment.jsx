/**
 * AGRA Chat Enhancement Phase 5 — Drawing Attachment
 * Preview and manage attached drawing files in chat.
 */

import { useState } from 'react';
import { FileImage, X, FileText, Loader2 } from 'lucide-react';

export default function DrawingAttachment({ file, onRemove, isUploading = false, isDark = false }) {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [isImage, setIsImage] = useState(false);

  // Generate preview for images
  useState(() => {
    if (file.type.startsWith('image/')) {
      setIsImage(true);
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [file]);

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const getFileIcon = () => {
    if (file.type === 'application/pdf') return <FileText size={20} color="#ef4444" />;
    return <FileImage size={20} color="#3b82f6" />;
  };

  const styles = {
    container: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      padding: '12px',
      background: isDark ? 'rgba(30, 41, 59, 0.8)' : 'rgba(255, 255, 255, 0.9)',
      borderRadius: '10px',
      border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
      maxWidth: '300px',
    },
    preview: {
      width: '48px',
      height: '48px',
      borderRadius: '6px',
      objectFit: 'cover',
      background: isDark ? '#1e293b' : '#f1f5f9',
    },
    iconContainer: {
      width: '48px',
      height: '48px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: isDark ? '#1e293b' : '#f1f5f9',
      borderRadius: '6px',
    },
    info: {
      flex: 1,
      minWidth: 0,
    },
    filename: {
      fontSize: '13px',
      fontWeight: 500,
      color: isDark ? '#e2e8f0' : '#1e293b',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
    },
    size: {
      fontSize: '11px',
      color: isDark ? '#64748b' : '#94a3b8',
      marginTop: '2px',
    },
    removeButton: {
      padding: '6px',
      borderRadius: '6px',
      border: 'none',
      background: 'transparent',
      cursor: isUploading ? 'not-allowed' : 'pointer',
      opacity: isUploading ? 0.5 : 1,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
    loadingOverlay: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      borderRadius: '6px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
  };

  return (
    <div style={{ ...styles.container, position: 'relative' }}>
      {isImage && previewUrl ? (
        <img src={previewUrl} alt={file.name} style={styles.preview} />
      ) : (
        <div style={styles.iconContainer}>
          {getFileIcon()}
        </div>
      )}

      <div style={styles.info}>
        <div style={styles.filename} title={file.name}>
          {file.name}
        </div>
        <div style={styles.size}>
          {formatSize(file.size)}
        </div>
      </div>

      {!isUploading && (
        <button
          style={styles.removeButton}
          onClick={onRemove}
          title="Remove file"
        >
          <X size={16} color={isDark ? '#94a3b8' : '#64748b'} />
        </button>
      )}

      {isUploading && (
        <div style={styles.loadingOverlay}>
          <Loader2 size={20} color="#fff" style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      )}
    </div>
  );
}
