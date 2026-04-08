import React, { createContext, useContext, useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import Usage from './pages/Usage'
import AuditLogs from './pages/AuditLogs'
import Documents from './pages/Documents'
import Agents from './pages/Agents'

export const AuthContext = createContext(null)

export function useAuth() {
  return useContext(AuthContext)
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="loading-container" style={{ height: '100vh' }}>
      <div className="spinner"></div>
      <span>Loading AGRA...</span>
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('agra_token')
    const userData = localStorage.getItem('agra_user')
    if (token && userData) {
      setUser(JSON.parse(userData))
    }
    setLoading(false)
  }, [])

  const login = (userData, token) => {
    localStorage.setItem('agra_token', token)
    localStorage.setItem('agra_user', JSON.stringify(userData))
    setUser(userData)
  }

  const logout = () => {
    localStorage.removeItem('agra_token')
    localStorage.removeItem('agra_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      <BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: '#141c35',
              color: '#e8edf8',
              border: '1px solid #1e2d52',
            }
          }}
        />
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/users" element={<Users />} />
                  <Route path="/usage" element={<Usage />} />
                  <Route path="/audit" element={<AuditLogs />} />
                  <Route path="/documents" element={<Documents />} />
                  <Route path="/agents" element={<Agents />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  )
}
