import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { getToken, setToken, getDashboardUrl } from './utils/auth';
import Chat from './pages/Chat';
import Generate from './pages/Generate';
import Drawing from './pages/Drawing';
import Compliance from './pages/Compliance';

function ProtectedRoute({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    
    if (urlToken && urlToken !== 'null' && urlToken !== '') {
      setToken(urlToken);
      setIsAuthenticated(true);
      window.history.replaceState({}, document.title, window.location.pathname);
    } else {
      const storedToken = getToken();
      if (storedToken && storedToken !== 'null' && storedToken !== '') {
        setIsAuthenticated(true);
      } else {
        // Instead of redirecting immediately, set an error state so we can see what's going wrong
        setIsAuthenticated('error');
      }
    }
  }, []);

  if (isAuthenticated === 'error') {
    return (
      <div style={{ padding: 40, color: 'var(--text-primary)', background: 'var(--bg-page)', minHeight: '100vh' }}>
        <h1>Authentication Error</h1>
        <p>No valid token found. Cannot load Agent UI.</p>
        <p>Current URL: {window.location.href}</p>
        <button onClick={() => window.location.href = getDashboardUrl('/login')}>Go to Login</button>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return children;
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Chat />
          </ProtectedRoute>
        }
      />
      <Route
        path="/generate"
        element={
          <ProtectedRoute>
            <Generate />
          </ProtectedRoute>
        }
      />
      <Route
        path="/drawing"
        element={
          <ProtectedRoute>
            <Drawing />
          </ProtectedRoute>
        }
      />
      <Route
        path="/compliance"
        element={
          <ProtectedRoute>
            <Compliance />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
