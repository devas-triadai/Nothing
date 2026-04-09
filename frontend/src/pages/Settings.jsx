import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getToken, logout, getUser } from '../utils/auth';

const API = '/api';

async function apiFetch(path, opts = {}) {
  const token = getToken();
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {})
    }
  });
  if (res.status === 401) {
    logout();
    return null;
  }
  return res.json().catch(() => null);
}

export default function Settings() {
  const navigate = useNavigate();
  const user = getUser();
  const [activeTab, setActiveTab] = useState('general');
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({
    siteName: 'AGRA Super Admin',
    siteDescription: 'Administrative Control Panel',
    maintenanceMode: false,
    allowRegistration: true,
    sessionTimeout: 30,
    maxLoginAttempts: 5,
    twoFactorRequired: false,
    emailNotifications: true,
    slackWebhook: '',
    smtpHost: 'smtp.agra.gov.in',
    smtpPort: 587
  });

  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }
  }, []);

  const handleSave = async () => {
    setSaving(true);
    // Simulate save
    setTimeout(() => {
      setSaving(false);
      alert('Settings saved successfully!');
    }, 1000);
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0b1020 0%, #111a2e 100%)',
      color: '#fff',
      fontFamily: 'Inter, system-ui, sans-serif',
      padding: '24px'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 32,
        paddingBottom: 20,
        borderBottom: '1px solid rgba(70,110,255,0.2)'
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800 }}>⚙️ System Settings</h1>
          <p style={{ margin: '4px 0 0', color: '#7a90b8', fontSize: 13 }}>
            Configure global platform parameters and security
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: '#9fb0d0', fontSize: 13 }}>{user?.username || 'Admin'}</span>
          <button onClick={() => logout()} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(255,80,80,0.3)',
            background: 'rgba(255,80,80,0.1)', color: '#ff9b9b', cursor: 'pointer', fontSize: 13, fontWeight: 600
          }}>Logout</button>
        </div>
      </div>

      {/* Nav */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 32, flexWrap: 'wrap' }}>
        {[
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'Users', path: '/users' },
          { label: 'Reports', path: '/reports' },
          { label: 'Agents', path: '/agents' },
          { label: 'Documents', path: '/documents' },
          { label: 'Audit Logs', path: '/audit-logs' },
          { label: 'Usage Analytics', path: '/usage-analytics' }
        ].map(item => (
          <button key={item.path} onClick={() => navigate(item.path)} style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid rgba(70,110,255,0.3)',
            background: 'rgba(36,99,255,0.1)', color: '#7ab4ff', cursor: 'pointer', fontSize: 13, fontWeight: 500
          }}>{item.label}</button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 32 }}>
        {/* Sidebar Tabs */}
        <div style={{ width: 200, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {['general', 'security', 'notifications', 'email'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                textAlign: 'left', padding: '12px 16px', borderRadius: 8, border: 'none',
                background: activeTab === tab ? 'rgba(36,99,255,0.15)' : 'transparent',
                color: activeTab === tab ? '#7ab4ff' : '#7a90b8',
                cursor: 'pointer', fontSize: 14, fontWeight: 600, textTransform: 'capitalize'
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <div style={{
          flex: 1, background: 'rgba(10,15,30,0.8)', border: '1px solid rgba(70,110,255,0.2)',
          borderRadius: 14, padding: 32
        }}>
          {activeTab === 'general' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 14, fontWeight: 600, color: '#c8d8f0' }}>Site Name</label>
                <input name="siteName" value={settings.siteName} onChange={handleChange} style={{
                  background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '10px 16px', borderRadius: 8, outline: 'none'
                }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 14, fontWeight: 600, color: '#c8d8f0' }}>Site Description</label>
                <textarea name="siteDescription" value={settings.siteDescription} onChange={handleChange} style={{
                  background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '10px 16px', borderRadius: 8, outline: 'none', minHeight: 80
                }} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input type="checkbox" name="maintenanceMode" checked={settings.maintenanceMode} onChange={handleChange} style={{ width: 18, height: 18 }} />
                <label style={{ fontSize: 14, color: '#c8d8f0' }}>Maintenance Mode</label>
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 14, fontWeight: 600, color: '#c8d8f0' }}>Session Timeout (minutes)</label>
                <input type="number" name="sessionTimeout" value={settings.sessionTimeout} onChange={handleChange} style={{
                  background: '#1a2236', border: '1px solid #2d3b5a', color: '#fff', padding: '10px 16px', borderRadius: 8, outline: 'none', width: 100
                }} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input type="checkbox" name="twoFactorRequired" checked={settings.twoFactorRequired} onChange={handleChange} style={{ width: 18, height: 18 }} />
                <label style={{ fontSize: 14, color: '#c8d8f0' }}>Require 2FA for all Admins</label>
              </div>
            </div>
          )}

          <div style={{ marginTop: 40, paddingTop: 24, borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '12px 32px', borderRadius: 10, border: 'none',
                background: '#2463ff', color: '#fff', cursor: 'pointer', fontSize: 14, fontWeight: 600,
                opacity: saving ? 0.7 : 1
              }}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
