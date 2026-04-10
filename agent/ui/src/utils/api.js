/**
 * AGRA Agent — API Client
 * Centralized axios-based API client.
 */

import axios from 'axios';
import { getToken, logout } from './auth';

export function getApiUrl(path = '') {
  const isBrowser = typeof window !== 'undefined';
  if (isBrowser && window.location.hostname.includes('runpod.net')) {
    return window.location.origin.replace('7860', '8005') + path;
  }
  const podId = import.meta.env.VITE_POD_ID || '';
  if (podId && podId !== 'your-runpod-pod-id-here') {
    return `https://${podId}-8005.proxy.runpod.net${path}`;
  }
  return `http://localhost:8005${path}`;
}

const api = axios.create({
  baseURL: getApiUrl('/api/agent'),
  timeout: 120000,
});

// Request interceptor — attach auth token
api.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
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

export default api;
