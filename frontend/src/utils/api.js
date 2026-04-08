import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('agra_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('agra_token')
      localStorage.removeItem('agra_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Auth
export const loginApi = (username, password) => {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  return axios.post('/api/auth/login', formData)
}
export const logoutApi = () => api.post('/auth/logout')
export const getMeApi = () => api.get('/auth/me')

// Dashboard
export const getDashboardStats = () => api.get('/dashboard/stats')
export const getRecentActivity = (limit = 10) => api.get(`/dashboard/activity?limit=${limit}`)

// Users
export const getUsers = (params) => api.get('/users/', { params })
export const createUser = (data) => api.post('/users/', data)
export const updateUser = (id, data) => api.put(`/users/${id}`, data)
export const deleteUser = (id) => api.delete(`/users/${id}`)
export const changePassword = (id, password) => api.put(`/users/${id}/password`, { new_password: password })

// Usage
export const getUsageLogs = (params) => api.get('/usage/', { params })
export const getUsageSummary = (days) => api.get(`/usage/summary?days=${days}`)
export const getTopUsers = (params) => api.get('/usage/top-users', { params })

// Audit
export const getAuditLogs = (params) => api.get('/audit/', { params })

// Documents
export const getDocuments = (params) => api.get('/documents/', { params })
export const updateDocument = (id, data) => api.put(`/documents/${id}`, data)
export const deleteDocument = (id) => api.delete(`/documents/${id}`)

// Agents
export const getAgentConfigs = () => api.get('/agents/')
export const updateAgentConfig = (id, data) => api.put(`/agents/${id}`, data)
export const getHouseRules = () => api.get('/agents/house-rules')
export const updateHouseRules = (rules) => api.put('/agents/house-rules', { house_rules: rules })

export default api
