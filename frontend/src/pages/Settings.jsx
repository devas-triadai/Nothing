import { useState, useEffect } from 'react';
import { apiFetch } from '../utils/api';
import { getUser } from '../utils/auth';
import { Settings as SettingsIcon, User, Bell, Shield, Key, Save, Eye, EyeOff } from 'lucide-react';

const SectionCard = ({ title, icon: Icon, children }) => (
  <div style={{ background: 'var(--surface)', borderRadius: '12px', border: '1px solid var(--border)', marginBottom: '20px', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
    <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '10px' }}>
      <Icon size={16} color="#1e6bff" />
      <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>{title}</h2>
    </div>
    <div style={{ padding: '20px' }}>{children}</div>
  </div>
);

const FormRow = ({ label, children, hint }) => (
  <div style={{ marginBottom: '16px' }}>
    <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '6px' }}>{label}</label>
    {children}
    {hint && <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: '4px 0 0' }}>{hint}</p>}
  </div>
);

const inputStyle = {
  width: '100%',
  padding: '9px 12px',
  borderRadius: '8px',
  border: '1px solid var(--border)',
  background: 'var(--surface)',
  color: 'var(--text-primary)',
  fontSize: '13px',
  outline: 'none',
  boxSizing: 'border-box',
};

export default function Settings() {
  const [profile, setProfile] = useState({ name: '', email: '', role: '' });
  const [passwords, setPasswords] = useState({ current: '', new_pass: '', confirm: '' });
  const [showPw, setShowPw] = useState(false);
  const [notifications, setNotifications] = useState({ email_alerts: true, system_alerts: true, audit_alerts: false });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    const user = getUser();
    if (user) {
      setProfile({ name: user.name || user.username || '', email: user.email || '', role: user.role || '' });
    }
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const data = await apiFetch('/settings/');
      if (data?.notifications) setNotifications(data.notifications);
    } catch (err) {
      console.error('Settings fetch error:', err);
    }
  };

  const showMsg = (text, type = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 3000);
  };

  const handleProfileSave = async () => {
    setSaving(true);
    try {
      const data = await apiFetch('/settings/profile', { method: 'PUT', body: JSON.stringify(profile) });
      if (data) showMsg('Profile updated successfully');
      else showMsg('Failed to update profile', 'error');
    } catch (err) {
      showMsg('Error updating profile', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordChange = async () => {
    if (passwords.new_pass !== passwords.confirm) {
      showMsg('Passwords do not match', 'error');
      return;
    }
    setSaving(true);
    try {
      const data = await apiFetch('/settings/password', {
        method: 'PUT',
        body: JSON.stringify({ current_password: passwords.current, new_password: passwords.new_pass })
      });
      if (data?.success) {
        showMsg('Password changed successfully');
        setPasswords({ current: '', new_pass: '', confirm: '' });
      } else {
        showMsg(data?.error || 'Failed to change password', 'error');
      }
    } catch (err) {
      showMsg('Error changing password', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleNotificationSave = async () => {
    setSaving(true);
    try {
      const data = await apiFetch('/settings/notifications', { method: 'PUT', body: JSON.stringify(notifications) });
      if (data) showMsg('Notification settings saved');
      else showMsg('Failed to save notifications', 'error');
    } catch (err) {
      showMsg('Error saving notifications', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '720px' }}>
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
          <SettingsIcon size={24} color="#1e6bff" />
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Settings</h1>
        </div>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0, paddingLeft: '36px' }}>
          Manage your account and system preferences
        </p>
      </div>

      {message && (
        <div style={{
          padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', fontSize: '13px', fontWeight: 500,
          background: message.type === 'success' ? 'rgba(0,200,83,0.15)' : 'rgba(213,0,0,0.15)',
          color: message.type === 'success' ? '#00c853' : '#d50000',
          border: `1px solid ${message.type === 'success' ? 'rgba(0,200,83,0.3)' : 'rgba(213,0,0,0.3)'}`,
        }}>{message.text}</div>
      )}

      <SectionCard title="Profile Information" icon={User}>
        <FormRow label="Full Name">
          <input style={inputStyle} value={profile.name} onChange={e => setProfile(p => ({ ...p, name: e.target.value }))} placeholder="Enter your name" />
        </FormRow>
        <FormRow label="Email Address">
          <input style={inputStyle} type="email" value={profile.email} onChange={e => setProfile(p => ({ ...p, email: e.target.value }))} placeholder="Enter your email" />
        </FormRow>
        <FormRow label="Role">
          <input style={{ ...inputStyle, background: 'var(--surface-hover)', cursor: 'not-allowed' }} value={profile.role} readOnly />
        </FormRow>
        <button onClick={handleProfileSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#1e6bff', color: 'white', fontSize: '13px', cursor: 'pointer', fontWeight: 500 }}>
          <Save size={14} /> {saving ? 'Saving...' : 'Save Profile'}
        </button>
      </SectionCard>

      <SectionCard title="Change Password" icon={Key}>
        <FormRow label="Current Password">
          <div style={{ position: 'relative' }}>
            <input
              style={{ ...inputStyle, paddingRight: '40px' }}
              type={showPw ? 'text' : 'password'}
              value={passwords.current}
              onChange={e => setPasswords(p => ({ ...p, current: e.target.value }))}
              placeholder="Current password"
            />
            <button onClick={() => setShowPw(v => !v)} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
              {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </FormRow>
        <FormRow label="New Password">
          <input style={inputStyle} type="password" value={passwords.new_pass} onChange={e => setPasswords(p => ({ ...p, new_pass: e.target.value }))} placeholder="New password" />
        </FormRow>
        <FormRow label="Confirm New Password">
          <input style={inputStyle} type="password" value={passwords.confirm} onChange={e => setPasswords(p => ({ ...p, confirm: e.target.value }))} placeholder="Confirm new password" />
        </FormRow>
        <button
          onClick={handlePasswordChange}
          disabled={saving || !passwords.current || !passwords.new_pass}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#1e6bff', color: 'white', fontSize: '13px', cursor: 'pointer', fontWeight: 500, opacity: (!passwords.current || !passwords.new_pass) ? 0.6 : 1 }}
        >
          <Key size={14} /> {saving ? 'Saving...' : 'Change Password'}
        </button>
      </SectionCard>

      <SectionCard title="Notification Preferences" icon={Bell}>
        {[
          { key: 'email_alerts', label: 'Email Alerts', desc: 'Receive important alerts via email' },
          { key: 'system_alerts', label: 'System Notifications', desc: 'In-app system notifications' },
          { key: 'audit_alerts', label: 'Audit Log Alerts', desc: 'Notifications for critical audit events' },
        ].map(({ key, label, desc }) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>{label}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>{desc}</div>
            </div>
            <button
              onClick={() => setNotifications(n => ({ ...n, [key]: !n[key] }))}
              style={{ width: 44, height: 24, borderRadius: '12px', border: 'none', cursor: 'pointer', background: notifications[key] ? '#1e6bff' : 'var(--border)', position: 'relative', transition: 'background 0.2s' }}
            >
              <span style={{ position: 'absolute', top: '3px', width: 18, height: 18, borderRadius: '50%', background: 'white', left: notifications[key] ? '23px' : '3px', transition: 'left 0.2s' }} />
            </button>
          </div>
        ))}
        <button onClick={handleNotificationSave} disabled={saving} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '9px 18px', borderRadius: '8px', border: 'none', background: '#1e6bff', color: 'white', fontSize: '13px', cursor: 'pointer', fontWeight: 500, marginTop: '16px' }}>
          <Save size={14} /> Save Preferences
        </button>
      </SectionCard>
    </div>
  );
}
