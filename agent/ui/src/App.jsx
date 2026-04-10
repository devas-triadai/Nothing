import { Routes, Route, Navigate } from 'react-router-dom';
import { getToken } from './utils/auth';
import Chat from './pages/Chat';
import Upload from './pages/Upload';
import Generate from './pages/Generate';
import Compliance from './pages/Compliance';

function ProtectedRoute({ children }) {
  const token = getToken();
  if (!token) {
    const podId = import.meta.env.VITE_POD_ID || '';
    if (podId && podId !== 'your-runpod-pod-id-here') {
      window.location.href = `https://${podId}-3000.proxy.runpod.net/login`;
    } else {
      window.location.href = 'http://localhost:3000/login';
    }
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
