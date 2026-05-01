/**
 * AGRA Agent — Auth Utilities
 * Manages JWT tokens and authentication state.
 */

const TOKEN_KEY = 'agra_token';
const USER_KEY = 'agra_user';

/**
 * Read the auth token from localStorage.
 */
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Store auth token.
 */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Remove auth token (logout).
 */
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Get stored user info.
 */
export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Store user info.
 */
export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Get Authorization headers for API calls.
 */
export function authHeaders() {
  const token = getToken();
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

/**
 * Get the dashboard login URL based on environment.
 */
export function getDashboardUrl(path = '/login') {
  const adminPort = import.meta.env.VITE_ADMIN_PORT || '3000';
  const uiPort = import.meta.env.VITE_AGENT_UI_PORT || '7860';
  if (typeof window !== 'undefined' && window.location.hostname.includes('runpod.net')) {
    return window.location.origin.replace(uiPort, adminPort) + path;
  }
  const podId = import.meta.env.VITE_POD_ID || '';
  if (podId && podId !== 'your-runpod-pod-id-here') {
    return `https://${podId}-${adminPort}.proxy.runpod.net${path}`;
  }
  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${adminPort}${path}`;
  }
  return `http://localhost:${adminPort}${path}`;
}

/**
 * Enforce authentication — redirect if no token.
 */
export function requireAuth() {
  const token = getToken();
  if (!token) {
    window.location.href = getDashboardUrl('/login');
    return false;
  }
  return true;
}

/**
 * Logout — clear everything, redirect to dashboard.
 */
export function logout() {
  clearToken();
  window.location.href = getDashboardUrl('/login');
}

/**
 * Decode a JWT payload (no verification — just decode).
 */
export function decodeToken(token) {
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}
