import { useState } from 'react';
import { NavLink, useNavigate, Outlet } from 'react-router-dom';
import { useAuth } from '../App';
import auth from '../utils/auth';
import {
  LayoutDashboard, Users, BarChart3, ScrollText,
  FileText, Bot, LogOut, Menu, X, Anchor, Shield,
  Settings, ClipboardList
} from 'lucide-react';

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/users', icon: Users, label: 'User Management' },
  { path: '/usage-analytics', icon: BarChart3, label: 'Usage Analytics' },
  { path: '/audit-logs', icon: ScrollText, label: 'Audit Logs' },
  { path: '/documents', icon: FileText, label: 'Documents' },
  { path: '/agents', icon: Bot, label: 'Agent Config' },
  { path: '/reports', icon: ClipboardList, label: 'Reports' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export default function Layout() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const handleLogout = async () => {
    await auth.logout();
    setUser(null);
    navigate('/login');
  };

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0b1020', color: '#fff' }}>
      {/* Sidebar */}
      <aside style={{
        width: sidebarOpen ? 260 : 80,
        background: 'rgba(10, 15, 30, 0.95)',
        borderRight: '1px solid rgba(70, 110, 255, 0.2)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'all 0.3s ease'
      }}>
        <div style={{ padding: '24px', display: 'flex', alignItems: 'center', gap: 12, minHeight: 72 }}>
          <div style={{
            width: 40, height: 40, flexShrink: 0,
            background: 'linear-gradient(135deg, #1e6bff, #00c8e0)',
            borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Shield size={20} color="white" strokeWidth={2.5} />
          </div>
          {sidebarOpen && (
            <div>
              <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: '0.05em' }}>AGRA</div>
              <div style={{ fontSize: 10, color: '#7ab4ff', fontWeight: 600 }}>SUPER ADMIN</div>
            </div>
          )}
        </div>

        <nav style={{ flex: 1, padding: '12px 8px', overflowY: 'auto' }}>
          {navItems.map(({ path, icon: Icon, label }) => (
            <NavLink
              key={path}
              to={path}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 12px',
                borderRadius: 8,
                textDecoration: 'none',
                marginBottom: 2,
                background: isActive ? 'rgba(36, 99, 255, 0.15)' : 'transparent',
                color: isActive ? '#7ab4ff' : '#7a90b8',
                fontWeight: isActive ? 600 : 400,
                fontSize: 14,
                borderLeft: isActive ? '3px solid #2463ff' : '3px solid transparent',
                transition: 'all 0.2s'
              })}
            >
              <Icon size={18} style={{ flexShrink: 0 }} />
              {sidebarOpen && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        <div style={{ padding: '16px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <button
            onClick={handleLogout}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 12,
              padding: '10px 12px', borderRadius: 8, border: 'none',
              background: 'rgba(255, 80, 80, 0.05)', color: '#ff9b9b',
              cursor: 'pointer', fontSize: 14, fontWeight: 600
            }}
          >
            <LogOut size={18} />
            {sidebarOpen && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main style={{ flex: 1, overflowY: 'auto', position: 'relative' }}>
        <header style={{
          height: 64, display: 'flex', alignItems: 'center', padding: '0 24px',
          background: 'rgba(10, 15, 30, 0.5)', borderBottom: '1px solid rgba(255,255,255,0.05)'
        }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ background: 'none', border: 'none', color: '#7a90b8', cursor: 'pointer' }}
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div style={{ flex: 1 }}></div>
          <div style={{ fontSize: 13, color: '#7a90b8' }}>
            Welcome, <span style={{ color: '#fff', fontWeight: 600 }}>{user?.username || 'Admin'}</span>
          </div>
        </header>
        <div style={{ padding: 0 }}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
