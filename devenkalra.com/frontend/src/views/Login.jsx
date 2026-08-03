import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getGoogleRedirectUri, startGoogleOAuthRedirect } from '../utils/googleOAuth';

export const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showAdminLogin, setShowAdminLogin] = useState(false);

  const [googleClientId, setGoogleClientId] = useState('');
  const [githubClientId, setGithubClientId] = useState('');

  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';
  const isLocalHost =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

  useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch('/api/auth/config/');
        const data = await res.json();
        if (data.googleClientId) setGoogleClientId(data.googleClientId);
        if (data.githubClientId) setGithubClientId(data.githubClientId);
      } catch (err) {
        console.error('Failed to load auth config:', err);
      }
    };
    fetchConfig();
  }, []);

  const handleGoogleLogin = () => {
    if (!googleClientId) return;
    setError('');
    // Full-page redirect is more reliable than GIS popup (popup often reports
    // "cancelled" right after account selection).
    startGoogleOAuthRedirect({ clientId: googleClientId, returnPath: from });
  };

  const handleGithubLogin = () => {
    if (!githubClientId) return;
    localStorage.setItem('authRedirectPath', from);
    const redirectUri = window.location.origin + '/login/github/callback';
    const authUrl = `https://github.com/login/oauth/authorize?client_id=${githubClientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=user%3Aemail`;
    window.location.href = authUrl;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    const result = await login(username, password);
    setSubmitting(false);

    if (result.success) {
      navigate(from, { replace: true });
    } else {
      setError(result.error);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem 0' }}>
      <div
        className="auth-card"
        style={{
          maxWidth: '420px',
          width: '100%',
          padding: '2.5rem',
          border: '1px solid var(--border-dark)',
          boxShadow: 'none',
        }}
      >
        <h2
          style={{
            borderBottom: 'none',
            marginTop: 0,
            marginBottom: '2rem',
            textAlign: 'center',
            fontFamily: 'var(--font-serif)',
          }}
        >
          Sign In
        </h2>

        {error && (
          <div className="error-message" style={{ marginBottom: '1.5rem' }}>
            {error}
          </div>
        )}

        {!showAdminLogin ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              alignItems: 'center',
              width: '100%',
            }}
          >
            {submitting ? (
              <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>Verifying login...</div>
            ) : (
              <>
                {googleClientId && (
                  <button
                    type="button"
                    onClick={handleGoogleLogin}
                    className="social-auth-btn social-auth-btn--google"
                  >
                    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                      <path
                        fill="#EA4335"
                        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
                      />
                      <path
                        fill="#4285F4"
                        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
                      />
                      <path
                        fill="#FBBC05"
                        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
                      />
                      <path
                        fill="#34A853"
                        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
                      />
                    </svg>
                    Sign In with Google
                  </button>
                )}

                {githubClientId && (
                  <button
                    type="button"
                    onClick={handleGithubLogin}
                    className="social-auth-btn social-auth-btn--github"
                  >
                    <svg height="20" width="20" viewBox="0 0 16 16" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
                      />
                    </svg>
                    Sign In with GitHub
                  </button>
                )}

                <div
                  style={{
                    marginTop: '1.5rem',
                    borderTop: '1px solid var(--border-color)',
                    width: '100%',
                    paddingTop: '1rem',
                    textAlign: 'center',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setShowAdminLogin(true)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent-color)',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      textDecoration: 'underline',
                    }}
                  >
                    Admin staff sign in
                  </button>
                </div>

                {googleClientId && isLocalHost && (
                  <p
                    style={{
                      margin: '1rem 0 0',
                      fontSize: '0.72rem',
                      color: 'var(--text-muted)',
                      lineHeight: 1.45,
                      textAlign: 'left',
                      wordBreak: 'break-all',
                    }}
                  >
                    Google redirect URI (must match Console):
                    <br />
                    <code style={{ fontSize: '0.68rem' }}>{getGoogleRedirectUri()}</code>
                  </p>
                )}
              </>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="username">
                Username
              </label>
              <input
                type="text"
                id="username"
                className="form-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={submitting}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">
                Password
              </label>
              <input
                type="password"
                id="password"
                className="form-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={submitting}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '2rem' }}>
              <button
                type="submit"
                className="editorial-button"
                disabled={submitting}
                style={{ margin: 0 }}
              >
                {submitting ? 'Signing In...' : 'Unlock Site'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowAdminLogin(false);
                  setError('');
                }}
                className="editorial-button"
                style={{
                  margin: 0,
                  background: 'none',
                  color: 'var(--text-color)',
                  border: '1px solid var(--border-color)',
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
