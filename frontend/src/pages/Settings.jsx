import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Settings = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('general');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
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
    smtpHost: '',
    smtpPort: 587,
    smtpUser: '',
    smtpPassword: '',
  });

  useEffect(() => {
    const token = localStorage.getItem('agra_token');
    if (!token) { navigate('/login'); return; }
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch('/api/settings', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSettings(prev => ({ ...prev, ...data.settings }));
      }
    } catch (err) {
      console.error('Settings fetch error:', err);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('agra_token');
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch (err) {
      console.error('Settings save error:', err);
    } finally {
      setSaving(false);
    }
  };

  const update = (key, value) => setSettings(prev => ({ ...prev, [key]: value }));

  const inputStyle = {
    width: '100%',
    padding: '9px 12px',
    borderRadius: '8px',
    border: '1px solid var(--border)',
    background: 'var(--bg)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    outline: 'none',
    boxSizing: 'border-box',
  };

  const labelStyle = {
    fontSize: '13px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    marginBottom: '6px',
    display: 'block',
  };

  const tabs = ['general', 'security', 'notifications', 'smtp'];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>Settings</h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>Configure system settings</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '10px 24px', borderRadius: '8px', border: 'none',
            background: saved ? '#00c853' : 'linear-gradient(135deg, #1e6bff, #3d8bff)',
            color: 'white', fontSize: '14px', cursor: saving ? 'not-allowed' : 'pointer',
            fontWeight: 600, transition: 'all 0.2s',
          }}
        >
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Changes'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
        {tabs.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '8px 20px', borderRadius: '8px',
              border: activeTab === tab ? 'none' : '1px solid var(--border)',
              background: activeTab === tab ? '#1e6bff' : 'var(--surface)',
              color: activeTab === tab ? 'white' : 'var(--text-secondary)',
              fontSize: '13px', cursor: 'pointer', fontWeight: 500, textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      <div style={{
        background: 'var(--surface)', borderRadius: '12px',
        border: '1px solid var(--border)', padding: '28px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)', maxWidth: '640px',
      }}>
        {activeTab === 'general' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={labelStyle}>Site Name</label>
              <input style={inputStyle} value={settings.siteName} onChange={e => update('siteName', e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Site Description</label>
              <input style={inputStyle} value={settings.siteDescription} onChange={e => update('siteDescription', e.target.value)} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={labelStyle}>Maintenance Mode</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Disable public access to the system</div>
              </div>
              <div
                onClick={() => update('maintenanceMode', !settings.maintenanceMode)}
                style={{
                  width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer',
                  background: settings.maintenanceMode ? '#1e6bff' : 'var(--border)',
                  position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                }}
              >
                <div style={{
                  position: 'absolute', top: '2px',
                  left: settings.maintenanceMode ? '22px' : '2px',
                  width: '20px', height: '20px', borderRadius: '50%',
                  background: 'white', transition: 'left 0.2s',
                }} />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={labelStyle}>Allow Registration</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Allow new users to register</div>
              </div>
              <div
                onClick={() => update('allowRegistration', !settings.allowRegistration)}
                style={{
                  width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer',
                  background: settings.allowRegistration ? '#1e6bff' : 'var(--border)',
                  position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                }}
              >
                <div style={{
                  position: 'absolute', top: '2px',
                  left: settings.allowRegistration ? '22px' : '2px',
                  width: '20px', height: '20px', borderRadius: '50%',
                  background: 'white', transition: 'left 0.2s',
                }} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'security' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={labelStyle}>Session Timeout (minutes)</label>
              <input type="number" style={inputStyle} value={settings.sessionTimeout} onChange={e => update('sessionTimeout', parseInt(e.target.value))} />
            </div>
            <div>
              <label style={labelStyle}>Max Login Attempts</label>
              <input type="number" style={inputStyle} value={settings.maxLoginAttempts} onChange={e => update('maxLoginAttempts', parseInt(e.target.value))} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={labelStyle}>Require 2FA</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Enforce two-factor authentication for all admins</div>
              </div>
              <div
                onClick={() => update('twoFactorRequired', !settings.twoFactorRequired)}
                style={{
                  width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer',
                  background: settings.twoFactorRequired ? '#1e6bff' : 'var(--border)',
                  position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                }}
              >
                <div style={{
                  position: 'absolute', top: '2px',
                  left: settings.twoFactorRequired ? '22px' : '2px',
                  width: '20px', height: '20px', borderRadius: '50%',
                  background: 'white', transition: 'left 0.2s',
                }} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'notifications' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={labelStyle}>Email Notifications</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Receive email alerts for critical events</div>
              </div>
              <div
                onClick={() => update('emailNotifications', !settings.emailNotifications)}
                style={{
                  width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer',
                  background: settings.emailNotifications ? '#1e6bff' : 'var(--border)',
                  position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                }}
              >
                <div style={{
                  position: 'absolute', top: '2px',
                  left: settings.emailNotifications ? '22px' : '2px',
                  width: '20px', height: '20px', borderRadius: '50%',
                  background: 'white', transition: 'left 0.2s',
                }} />
              </div>
            </div>
            <div>
              <label style={labelStyle}>Slack Webhook URL</label>
              <input style={inputStyle} placeholder="https://hooks.slack.com/..." value={settings.slackWebhook} onChange={e => update('slackWebhook', e.target.value)} />
            </div>
          </div>
        )}

        {activeTab === 'smtp' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={labelStyle}>SMTP Host</label>
              <input style={inputStyle} placeholder="smtp.example.com" value={settings.smtpHost} onChange={e => update('smtpHost', e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>SMTP Port</label>
              <input type="number" style={inputStyle} value={settings.smtpPort} onChange={e => update('smtpPort', parseInt(e.target.value))} />
            </div>
            <div>
              <label style={labelStyle}>SMTP Username</label>
              <input style={inputStyle} value={settings.smtpUser} onChange={e => update('smtpUser', e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>SMTP Password</label>
              <input type="password" style={inputStyle} value={settings.smtpPassword} onChange={e => update('smtpPassword', e.target.value)} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Settings;
