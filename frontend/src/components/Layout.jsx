import React, { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../App'
import { logoutApi } from '../utils/api'
import toast from 'react-hot-toast'
import {
  LayoutDashboard, Users, BarChart3, ScrollText,
  FileText, Bot, LogOut, Menu, X, Anchor, ChevronRight, Shield
} from 'lucide-react'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
  { path: '/users', icon: Users, label: 'User Management' },
  { path: '/usage', icon: BarChart3, label: 'Usage Analytics' },
  { path: '/audit', icon: ScrollText, label: 'Audit Logs' },
  { path: '/documents', icon: FileText, label: 'Documents' },
  { path: '/agents', icon: Bot, label: 'Agent Config' },
]

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const handleLogout = async () => {
    try {
      await logoutApi()
    } catch {}
    logout()
    navigate('/login')
    toast.success('Logged out successfully')
  }

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-primary)' }}>
      {/* Sidebar */}
      <aside style={{
        width: sidebarOpen ? '260px' : '72px',
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.25s ease',
        flexShrink: 0,
        overflow: 'hidden'
      }}>
        {/* Logo */}
        <div style={{
          padding: '20px 16px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          minHeight: '72px'
        }}>
          <div style={{
            width: '40px', height: '40px', flexShrink: 0,
            background: 'linear-gradient(135deg, #1e6bff, #00c8e0)',
            borderRadius: '10px',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Anchor size={20} color="white" strokeWidth={2.5} />
          </div>
          {sidebarOpen && (
            <div>
              <div style={{ fontWeight: 700, fontSize: '16px', letterSpacing: '0.05em', color: 'var(--text-primary)' }}>AGRA</div>
              <div style={{ fontSize: '10px', color: 'var(--accent-cyan)', fontWeight: 600, letterSpacing: '0.1em' }}>INDIAN COAST GUARD</div>
            </div>
          )}
        </div>

        {/* Nav items */}
        <nav style={{ flex: 1, padding: '12px 8px', overflowY: 'auto' }}>
          {navItems.map(({ path, icon: Icon, label }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '10px 12px',
                borderRadius: '8px',
                textDecoration: 'none',
                marginBottom: '2px',
                background: isActive ? 'rgba(30, 107, 255, 0.15)' : 'transparent',
                color: isActive ? 'var(--accent-blue-light)' : 'var(--text-secondary)',
                fontWeight: isActive ? 600 : 400,
                fontSize: '14px',
                borderLeft: isActive ? '3px solid var(--accent-blue)' : '3px solid transparent',
                transition: 'all 0.15s',
                whiteSpace: 'nowrap',
                overflow: 'hidden'
              })}
            >
              <Icon size={18} style={{ flexShrink: 0 }} />
              {sidebarOpen && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* User info + Logout */}
        <div style={{ padding: '12px 8px', borderTop: '1px solid var(--border)' }}>
          {sidebarOpen && (
            <div style={{
              padding: '12px',
              background: 'var(--bg-card)',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              marginBottom: '8px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <Shield size={14} color="var(--accent-gold)" />
                <span style={{ fontSize: '11px', color: 'var(--accent-gold)', fontWeight: 600 }}>SUPER ADMIN</span>
              </div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{user?.full_name}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>@{user?.username}</div>
            </div>
          )}
          <button
            onClick={handleLogout}
            style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              width: '100%', padding: '10px 12px',
              background: 'rgba(255, 77, 109, 0.1)',
              border: '1px solid rgba(255, 77, 109, 0.2)',
              borderRadius: '8px', cursor: 'pointer',
              color: 'var(--accent-red)', fontSize: '14px',
              fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden'
            }}
          >
            <LogOut size={16} style={{ flexShrink: 0 }} />
            {sidebarOpen && 'Logout'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top bar */}
        <header style={{
          height: '64px',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          padding: '0 24px', gap: '16px', flexShrink: 0
        }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{
              background: 'var(--bg-hover)',
              border: '1px solid var(--border)',
              borderRadius: '8px', padding: '8px',
              cursor: 'pointer', color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center'
            }}
          >
            {sidebarOpen ? <X size={16} /> : <Menu size={16} />}
          </button>

          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>AGRA Super Admin Dashboard</div>
          </div>

          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '6px 12px',
            background: 'rgba(16, 217, 121, 0.1)',
            border: '1px solid rgba(16, 217, 121, 0.2)',
            borderRadius: '20px'
          }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-green)' }} />
            <span style={{ fontSize: '12px', color: 'var(--accent-green)', fontWeight: 500 }}>System Online</span>
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, overflowY: 'auto' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
