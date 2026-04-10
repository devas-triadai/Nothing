/**
 * AGRA Agent — API Client
 * Centralized axios-based API client.
 */

import axios from 'axios';
import { getToken, logout } from './auth';

const api = axios.create({
  baseURL: '/api/agent',
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
