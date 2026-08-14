import { getApiBaseUrl, getLoginUrl } from '../utils/apiUrl';
import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { jwtDecode } from 'jwt-decode';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [loading, setLoading] = useState(true);

  const clearTokens = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
    setAccessToken(null);
    setUser(null);
  }, []);

  const refreshToken = useCallback(async () => {
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) {
      clearTokens();
      return null;
    }
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/auth/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      });
      if (!response.ok) throw new Error('Refresh failed');
      const data = await response.json();
      localStorage.setItem('access_token', data.access);
      setAccessToken(data.access);
      return data.access;
    } catch (error) {
      console.error('Token refresh failed:', error);
      clearTokens();
      return null;
    }
  }, [clearTokens]);

  useEffect(() => {
    let cancelled = false;

    const loadAuth = async () => {
      const token = localStorage.getItem('access_token');
      const userStr = localStorage.getItem('current_user');

      if (token && userStr) {
        try {
          const decoded = jwtDecode(token);
          if (decoded.exp * 1000 > Date.now()) {
            if (!cancelled) {
              setAccessToken(token);
              setUser(JSON.parse(userStr));
            }
          } else {
            // Keep loading=true until refresh settles so we don't bounce to /login.
            const newToken = await refreshToken();
            if (!cancelled && newToken) {
              setAccessToken(newToken);
              setUser(JSON.parse(userStr));
            }
          }
        } catch (error) {
          console.error('Invalid token:', error);
          if (!cancelled) clearTokens();
        }
        if (!cancelled) setLoading(false);
        return;
      }

      try {
        const r = await fetch(`${getApiBaseUrl()}/api/auth/user/`, { credentials: 'include' });
        const userData = r.ok ? await r.json() : null;
        if (!cancelled && userData) setUser(userData);
      } catch (_) {
        /* ignore */
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadAuth();

    const onTokenReceived = () => {
      const token = localStorage.getItem('access_token');
      const userStr = localStorage.getItem('current_user');
      if (!token || !userStr) return;
      try {
        const decoded = jwtDecode(token);
        if (decoded.exp * 1000 > Date.now()) {
          setAccessToken(token);
          setUser(JSON.parse(userStr));
        }
      } catch (_) {
        /* ignore */
      }
    };
    window.addEventListener('bldrdojo-auth-token-received', onTokenReceived);
    return () => {
      cancelled = true;
      window.removeEventListener('bldrdojo-auth-token-received', onTokenReceived);
    };
  }, [clearTokens, refreshToken]);

  const logout = async () => {
    if (accessToken) {
      try {
        await fetch(`${getApiBaseUrl()}/api/auth/logout/`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${accessToken}` },
        });
      } catch (error) {
        console.error('Logout error:', error);
      }
    }
    clearTokens();
    if (typeof window !== 'undefined') {
      window.location.href = getLoginUrl(window.location.pathname || '/app/gallery/');
    }
  };

  const updateUser = async (updates) => {
    const token = accessToken || localStorage.getItem('access_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (!token && !user) throw new Error('Not authenticated');
    const response = await fetch(`${getApiBaseUrl()}/api/auth/user/`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(updates),
      credentials: 'include',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.displayname?.[0] || error.username?.[0] || error.detail || 'Update failed'
      );
    }
    const data = await response.json();
    const updatedUser = { ...user, ...data };
    localStorage.setItem('current_user', JSON.stringify(updatedUser));
    setUser(updatedUser);
    return updatedUser;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        loading,
        logout,
        updateUser,
        refreshToken,
        isAuthenticated: !!user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
