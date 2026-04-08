import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../utils/auth'
import { useAuth } from '../App'

export default function Login() {
  const navigate = useNavigate()
  const { setUser } = useAuth()
  const [username, setUsername] = useState('agra_admin')
  const [password, setPassword] = useState('ICG@AGRA#2026')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showPwd, setShowPwd] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) {
      setError('Please enter credentials')
      return
    }
    setLoading(true)
    setError('')

    try {
      const data = await login(username, password)
      if (setUser && data.user) {
        setUser(data.user)
      }
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'grid',
      placeItems: 'center',
      background: 'linear-gradient(135deg, #0b1020 0%, #111a2e 100%)',
      color: '#fff',
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      <form onSubmit={handleSubmit} style={{
        width: '100%',
        maxWidth: 420,
        background: 'rgba(10,15,30,0.85)',
        border: '1px solid rgba(70,110,255,0.25)',
        borderRadius: 18,
        padding: '36px 32px',
        boxShadow: '0 24px 64px rgba(0,0,0,0.45)',
        boxSizing: 'border-box'
      }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            width: 56, height: 56,
            background: 'linear-gradient(135deg, #2463ff, #4a8bff)',
            borderRadius: 16,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 24,
            marginBottom: 12
          }}>🛡️</div>
          <h1 style={{ margin: '0 0 6px', fontSize: 28, fontWeight: 800, letterSpacing: '-0.5px' }}>
            AGRA
          </h1>
          <p style={{ margin: 0, color: '#7a90b8', fontSize: 14 }}>
            Indian Coast Guard — Super Admin Access
          </p>
        </div>

        {/* Username */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: '#9fb0d0', fontWeight: 500 }}>
            Username
          </label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            style={{
              width: '100%',
              padding: '11px 14px',
              borderRadius: 10,
              border: '1px solid #2b3b6b',
              background: '#0d1526',
              color: '#fff',
              fontSize: 15,
              outline: 'none',
              boxSizing: 'border-box'
            }}
          />
        </div>

        {/* Password */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: '#9fb0d0', fontWeight: 500 }}>
            Password
          </label>
          <div style={{ position: 'relative' }}>
            <input
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              style={{
                width: '100%',
                padding: '11px 44px 11px 14px',
                borderRadius: 10,
                border: '1px solid #2b3b6b',
                background: '#0d1526',
                color: '#fff',
                fontSize: 15,
                outline: 'none',
                boxSizing: 'border-box'
              }}
            />
            <button
              type="button"
              onClick={() => setShowPwd(!showPwd)}
              style={{
                position: 'absolute', right: 12, top: '50%',
                transform: 'translateY(-50%)',
                background: 'none', border: 'none',
                color: '#7a90b8', cursor: 'pointer', padding: 0
              }}
            >
              {showPwd ? '🙈' : '👁️'}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(255,80,80,0.12)',
            border: '1px solid rgba(255,80,80,0.25)',
            color: '#ff9b9b',
            padding: '10px 14px',
            borderRadius: 10,
            marginBottom: 16,
            fontSize: 14
          }}>
            ⚠️ {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          style={{
            width: '100%',
            padding: '13px',
            border: 0,
            borderRadius: 12,
            background: loading
              ? '#1b2d5c'
              : 'linear-gradient(90deg, #2463ff 0%, #4a8bff 100%)',
            color: '#fff',
            fontWeight: 700,
            fontSize: 15,
            cursor: loading ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s'
          }}
        >
          {loading ? 'Signing in...' : 'Access Dashboard'}
        </button>

        <p style={{ textAlign: 'center', marginTop: 20, color: '#4a5e8a', fontSize: 12 }}>
          Restricted access · Authorised personnel only
        </p>
      </form>
    </div>
  )
}
