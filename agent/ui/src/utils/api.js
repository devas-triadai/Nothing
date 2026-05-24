/**
 * AGRA Agent — API Client
 * Centralized axios-based API client.
 * Ports are configurable via VITE_ env vars.
 */

import axios from 'axios';
import { getToken, logout } from './auth';

const AGENT_API_PORT = import.meta.env.VITE_AGENT_API_PORT || '8005';
const AGENT_UI_PORT = import.meta.env.VITE_AGENT_UI_PORT || '7860';
const BACKEND_PORT = import.meta.env.VITE_BACKEND_PORT || '8000';

export function getApiUrl(path = '') {
  const isBrowser = typeof window !== 'undefined';
  if (isBrowser && window.location.hostname.includes('runpod.net')) {
    return window.location.origin.replace(AGENT_UI_PORT, AGENT_API_PORT) + path;
  }
  const podId = import.meta.env.VITE_POD_ID || '';
  if (podId && podId !== 'your-runpod-pod-id-here') {
    return `https://${podId}-${AGENT_API_PORT}.proxy.runpod.net${path}`;
  }
  if (isBrowser) {
    return `${window.location.protocol}//${window.location.hostname}:${AGENT_API_PORT}${path}`;
  }
  return `http://localhost:${AGENT_API_PORT}${path}`;
}

export function getBackendUrl(path = '') {
  const isBrowser = typeof window !== 'undefined';
  if (isBrowser && window.location.hostname.includes('runpod.net')) {
    return window.location.origin.replace(AGENT_UI_PORT, BACKEND_PORT) + path;
  }
  const podId = import.meta.env.VITE_POD_ID || '';
  if (podId && podId !== 'your-runpod-pod-id-here') {
    return `https://${podId}-${BACKEND_PORT}.proxy.runpod.net${path}`;
  }
  if (isBrowser) {
    return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}${path}`;
  }
  return `http://localhost:${BACKEND_PORT}${path}`;
}

const api = axios.create({
  baseURL: getApiUrl('/api/agent'),
  timeout: 120000,
});

// Request interceptor — attach auth token
api.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token && token !== 'null') {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor — handle 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      logout();
    }
    return Promise.reject(error);
  }
);

export const backendApi = axios.create({
  baseURL: getBackendUrl('/api'),
  timeout: 120000,
});

backendApi.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token && token !== 'null') {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

backendApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      logout();
    }
    return Promise.reject(error);
  }
);

export default api;
