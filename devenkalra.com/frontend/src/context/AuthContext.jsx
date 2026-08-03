import React, { createContext, useState, useEffect, useContext, useCallback, useMemo } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('authToken'));
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  // Social Login Modal state and triggers
  const [isSocialLoginModalOpen, setIsSocialLoginModalOpen] = useState(false);
  const [socialLoginCallback, setSocialLoginCallback] = useState(null);

  const API_URL = '/api';

  const handleLogoutState = useCallback(() => {
    localStorage.removeItem('authToken');
    setToken(null);
    setIsAuthenticated(false);
    setUser(null);
  }, []);

  const openSocialLoginModal = useCallback((onSuccess = null) => {
    setSocialLoginCallback(() => onSuccess);
    setIsSocialLoginModalOpen(true);
  }, []);

  const closeSocialLoginModal = useCallback(() => {
    setIsSocialLoginModalOpen(false);
    setSocialLoginCallback(null);
  }, []);

  useEffect(() => {
    const checkAuthStatus = async () => {
      const headers = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }

      try {
        const response = await fetch(`${API_URL}/auth/status/`, {
          headers: headers,
          credentials: 'include',
        });

        if (response.ok) {
          const data = await response.json();
          if (data.isAuthenticated) {
            setIsAuthenticated(true);
            setUser(data.user);
          } else {
            handleLogoutState();
          }
        } else {
          handleLogoutState();
        }
      } catch (error) {
        console.error('Error checking auth status:', error);
      } finally {
        setLoading(false);
      }
    };

    checkAuthStatus();
  }, [token, handleLogoutState]);

  const fetchCsrfToken = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/auth/csrf/`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        return data.csrfToken;
      }
    } catch (error) {
      console.error('Failed to fetch CSRF token:', error);
    }
    return null;
  }, []);

  const login = useCallback(
    async (username, password) => {
      try {
        const csrfToken = await fetchCsrfToken();
        const headers = {
          'Content-Type': 'application/json',
        };
        if (csrfToken) {
          headers['X-CSRFToken'] = csrfToken;
        }

        const response = await fetch(`${API_URL}/auth/login/`, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ username, password }),
          credentials: 'include',
        });

        const data = await response.json();

        if (response.ok) {
          localStorage.setItem('authToken', data.token);
          setToken(data.token);
          setIsAuthenticated(true);
          setUser(data.user);
          return { success: true };
        }
        return { success: false, error: data.detail || 'Login failed.' };
      } catch (error) {
        console.error('Login error:', error);
        return { success: false, error: 'Network error occurred.' };
      }
    },
    [fetchCsrfToken]
  );

  const applySocialLoginSuccess = useCallback((data) => {
    if (data.token) {
      localStorage.setItem('authToken', data.token);
      setToken(data.token);
    }
    setIsAuthenticated(true);
    setUser(data.user);
    return { success: true };
  }, []);

  /** Legacy GIS ID-token login (kept for API compatibility / tests). */
  const loginWithGoogle = useCallback(
    async (idToken) => {
      try {
        const csrfToken = await fetchCsrfToken();
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken;

        const response = await fetch(`${API_URL}/auth/social/google/`, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ id_token: idToken }),
          credentials: 'include',
        });

        const data = await response.json();
        if (response.ok) return applySocialLoginSuccess(data);
        return { success: false, error: data.detail || 'Google login failed.' };
      } catch (error) {
        console.error('Google login error:', error);
        return { success: false, error: 'Network error occurred.' };
      }
    },
    [fetchCsrfToken, applySocialLoginSuccess]
  );

  /** Preferred: OAuth authorization-code redirect callback. */
  const loginWithGoogleCode = useCallback(
    async (code, redirectUri) => {
      try {
        const csrfToken = await fetchCsrfToken();
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken;

        const response = await fetch(`${API_URL}/auth/social/google/`, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ code, redirect_uri: redirectUri }),
          credentials: 'include',
        });

        const data = await response.json();
        if (response.ok) return applySocialLoginSuccess(data);
        return { success: false, error: data.detail || 'Google login failed.' };
      } catch (error) {
        console.error('Google login error:', error);
        return { success: false, error: 'Network error occurred.' };
      }
    },
    [fetchCsrfToken, applySocialLoginSuccess]
  );

  const loginWithGithub = useCallback(
    async (code) => {
      try {
        const csrfToken = await fetchCsrfToken();
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken;

        const response = await fetch(`${API_URL}/auth/social/github/`, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ code }),
          credentials: 'include',
        });

        const data = await response.json();
        if (response.ok) {
          if (data.token) {
            localStorage.setItem('authToken', data.token);
            setToken(data.token);
          }
          setIsAuthenticated(true);
          setUser(data.user);
          return { success: true };
        }
        return { success: false, error: data.detail || 'GitHub login failed.' };
      } catch (error) {
        console.error('GitHub login error:', error);
        return { success: false, error: 'Network error occurred.' };
      }
    },
    [fetchCsrfToken]
  );

  const logout = useCallback(async () => {
    try {
      const csrfToken = await fetchCsrfToken();
      const headers = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Token ${token}`;
      }
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      await fetch(`${API_URL}/auth/logout/`, {
        method: 'POST',
        headers: headers,
        credentials: 'include',
      });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      handleLogoutState();
    }
  }, [fetchCsrfToken, token, handleLogoutState]);

  const value = useMemo(
    () => ({
      isAuthenticated,
      user,
      token,
      loading,
      login,
      logout,
      loginWithGoogle,
      loginWithGoogleCode,
      loginWithGithub,
      isSocialLoginModalOpen,
      openSocialLoginModal,
      closeSocialLoginModal,
      socialLoginCallback,
    }),
    [
      isAuthenticated,
      user,
      token,
      loading,
      login,
      logout,
      loginWithGoogle,
      loginWithGoogleCode,
      loginWithGithub,
      isSocialLoginModalOpen,
      openSocialLoginModal,
      closeSocialLoginModal,
      socialLoginCallback,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);
