import React, { useState } from 'react'
import { useAuth } from '../App'
import { loginApi } from '../utils/api'
import toast from 'react-hot-toast'
import { Anchor, Eye, EyeOff, Shield, Lock, User } from 'lucide-react'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    if (!username || !password) {
      toast.error('Please enter credentials')
      return
    }
    setLoading(true)
    try {
      const res = await loginApi(username, password)
      const { access_token, user } = res.data
      if (!user.is_superadmin) {
        toast.error('Access denied. Super Admin only.')
        return
      }
      login(user, access_token)
      toast.success(`Welcome, ${user.full_name}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-primary)',
      backgroundImage: 'radial-gradient(ellipse at 50% 0%, rgba(30, 107, 255, 0.08) 0%, transparent 60%)',
      padding: '24px'
    }}>
      <div style={{ width: '100%', maxWidth: '420px' }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <div style={{
            width: '72px', height: '72px',
            background: 'linear-gradient(135deg, #1e6bff, #00c8e0)',
            borderRadius: '20px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
            boxShadow: '0 8px 32px rgba(30, 107, 255, 0.3)'
          }}>
            <Anchor size={36} color="white" strokeWidth={2} />
          </div>
          <h1 style={{ fontSize: '28px', fontWeight: 800, letterSpacing: '0.08em', color: 'var(--text-primary)', marginBottom: '4px' }}>AGRA</h1>
          <p style={{ fontSize: '13px', color: 'var(--accent-cyan)', fontWeight: 600, letterSpacing: '0.12em' }}>AIR-GAPPED RETRIEVAL AGENT</p>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>Indian Coast Guard HQ</p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '16px',
          padding: '32px',
          boxShadow: '0 24px 64px rgba(0, 0, 0, 0.4)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
            <Shield size={16} color="var(--accent-gold)" />
            <span style={{ fontSize: '13px', color: 'var(--accent-gold)', fontWeight: 600 }}>SUPER ADMIN ACCESS</span>
          </div>

          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 500 }}>Username</label>
              <div style={{ position: 'relative' }}>
                <User size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="agra_admin"
                  style={{ paddingLeft: '38px' }}
                  autoComplete="username"
                />
              </div>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 500 }}>Password</label>
              <div style={{ position: 'relative' }}>
                <Lock size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input
                  type={showPwd ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Password"
                  style={{ paddingLeft: '38px', paddingRight: '40px' }}
                  autoComplete="current-password"
                />
                <button type="button" onClick={() => setShowPwd(!showPwd)} style={{
                  position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)',
                  display: 'flex', alignItems: 'center', padding: '4px'
                }}>
                  {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '12px',
                background: loading ? 'var(--border)' : 'linear-gradient(135deg, #1e6bff, #3d85ff)',
                border: 'none', borderRadius: '10px',
                color: 'white', fontSize: '15px', fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                boxShadow: loading ? 'none' : '0 4px 16px rgba(30, 107, 255, 0.35)',
                transition: 'all 0.2s'
              }}
            >
              {loading ? 'Authenticating...' : 'Access Dashboard'}
            </button>
          </form>
        </div>

        <p style={{ textAlign: 'center', marginTop: '20px', fontSize: '12px', color: 'var(--text-muted)' }}>
          Restricted Access — Authorized Personnel Only
        </p>
      </div>
    </div>
  )
}
