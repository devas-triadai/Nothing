export async function login(username, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    throw new Error(data.detail || 'Login failed')
  }

  localStorage.setItem('agra_token', data.access_token)
  localStorage.setItem('agra_user', JSON.stringify(data.user || {}))
  return data
}

export function getToken() {
  return localStorage.getItem('agra_token') || ''
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem('agra_user') || 'null')
  } catch {
    return null
  }
}

export function isAuthenticated() {
  return !!getToken()
}

export function authHeaders(extra = {}) {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra
  }
}

export async function logout() {
  const token = getToken()
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
  } catch (_) {}

  localStorage.removeItem('agra_token')
  localStorage.removeItem('agra_user')
  window.location.href = '/login'
}

// Legacy compat export
export const auth = {
  getToken,
  getUser,
  isAuthenticated,
  authHeaders,
  logout,
  setSession: (token, user) => {
    localStorage.setItem('agra_token', token)
    localStorage.setItem('agra_user', JSON.stringify(user))
  },
  clearSession: () => {
    localStorage.removeItem('agra_token')
    localStorage.removeItem('agra_user')
  }
}

export default auth
