import React, { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Login from './components/Login';
import Register from './components/Register';
import GoogleCallback from './components/GoogleCallback';
import AppsMenu from './components/AppsMenu';

const AUTH_MESSAGE_TYPE = 'bldrdojo-auth-token';

function AppShell({ children }) {
  const location = useLocation();
  const { user, logout, accessToken } = useAuth();
  const current = location.pathname.startsWith('/cad-app')
    ? 'cad'
    : location.pathname.startsWith('/food-app')
      ? 'food'
      : 'people';

  useEffect(() => {
    const handler = (event) => {
      if (event.data?.type === 'bldrdojo-app-ready' && accessToken && event.origin === window.location.origin) {
        event.source?.postMessage({
          type: AUTH_MESSAGE_TYPE,
          access_token: accessToken,
          refresh_token: localStorage.getItem('refresh_token'),
          user: localStorage.getItem('current_user'),
        }, event.origin);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [accessToken]);

  return (
    <div className="min-h-screen flex flex-col bg-gray-100 dark:bg-gray-900">
      <header className="flex items-center justify-between gap-4 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <nav className="flex items-center gap-4">
          <AppsMenu current={current} />
        </nav>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600 dark:text-gray-400 truncate max-w-[180px]">
            {user?.email}
          </span>
          <button
            onClick={logout}
            className="px-3 py-1 text-sm rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            Logout
          </button>
        </div>
      </header>
      <main className="flex-1 flex flex-col min-h-0">
        {children}
      </main>
    </div>
  );
}

function AppFrame({ src }) {
  return (
    <iframe
      src={src}
      title="App"
      className="w-full flex-1 border-0 min-h-[600px]"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
    />
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/auth/google/callback" element={<GoogleCallback />} />
      <Route
        path="/people-app/*"
        element={
          <PrivateRoute>
            <AppShell>
              <AppFrame src="/people-app/" />
            </AppShell>
          </PrivateRoute>
        }
      />
      <Route
        path="/cad-app/*"
        element={
          <PrivateRoute>
            <AppShell>
              <AppFrame src="/cad-app/" />
            </AppShell>
          </PrivateRoute>
        }
      />
      <Route
        path="/food-app/*"
        element={
          <PrivateRoute>
            <AppShell>
              <AppFrame src="/food-app/" />
            </AppShell>
          </PrivateRoute>
        }
      />
      <Route path="/" element={<Navigate to="/people-app" replace />} />
    </Routes>
  );
}
