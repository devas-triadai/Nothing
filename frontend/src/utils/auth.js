export const auth = {
  getToken: () => localStorage.getItem('agra_token'),

  getUser: () => {
    try {
      const user = localStorage.getItem('agra_user');
      return user ? JSON.parse(user) : null;
    } catch {
      return null;
    }
  },

  setSession: (token, user) => {
    localStorage.setItem('agra_token', token);
    localStorage.setItem('agra_user', JSON.stringify(user));
  },

  clearSession: () => {
    localStorage.removeItem('agra_token');
    localStorage.removeItem('agra_user');
  },

  isAuthenticated: () => {
    return !!localStorage.getItem('agra_token');
  },

  hasRole: (role) => {
    try {
      const user = JSON.parse(localStorage.getItem('agra_user') || '{}');
      return user.role === role;
    } catch {
      return false;
    }
  },

  login: async (email, password) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || 'Login failed');
    }
    const data = await res.json();
    auth.setSession(data.token, data.user);
    return data;
  },

  logout: async () => {
    try {
      const token = auth.getToken();
      if (token) {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      auth.clearSession();
    }
  },
};

export default auth;
