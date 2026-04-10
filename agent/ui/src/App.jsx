import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { getToken, setToken, getDashboardUrl } from './utils/auth';
import Chat from './pages/Chat';
import Upload from './pages/Upload';
import Generate from './pages/Generate';
import Compliance from './pages/Compliance';

function ProtectedRoute({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(!!getToken());

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    if (urlToken) {
      setToken(urlToken);
      setIsAuthenticated(true);
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (!getToken()) {
      window.location.href = getDashboardUrl('/login');
    }
  }, []);

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
        path="/upload"
        element={
          <ProtectedRoute>
            <Upload />
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
