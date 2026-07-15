import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showAdminLogin, setShowAdminLogin] = useState(false);

  const [googleClientId, setGoogleClientId] = useState('');
  const [githubClientId, setGithubClientId] = useState('');
  
  const { login, loginWithGoogle, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  // If already authenticated, redirect away
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
        console.error("Failed to load auth config:", err);
      }
    };
    fetchConfig();
  }, []);

  // Initialize Google Sign-In Button
  useEffect(() => {
    if (!googleClientId || isAuthenticated || showAdminLogin) return;

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = () => {
      if (window.google) {
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            setSubmitting(true);
            setError('');
            const res = await loginWithGoogle(response.credential);
            setSubmitting(false);
            if (res.success) {
              navigate(from, { replace: true });
            } else {
              setError(res.error || 'Failed to sign in with Google.');
            }
          }
        });
        window.google.accounts.id.renderButton(
          document.getElementById('google-signin-btn-login-page'),
          { theme: 'outline', size: 'large', width: 280 }
        );
      }
    };
    document.body.appendChild(script);
    return () => {
      try { document.body.removeChild(script); } catch (e) {}
    };
  }, [googleClientId, isAuthenticated, showAdminLogin, loginWithGoogle, navigate, from]);

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
      <div className="auth-card" style={{ maxWidth: '420px', width: '100%', padding: '2.5rem', border: '1px solid var(--border-dark)', boxShadow: 'none' }}>
        <h2 style={{ borderBottom: 'none', marginTop: 0, marginBottom: '2rem', textAlign: 'center', fontFamily: 'var(--font-serif)' }}>Sign In</h2>
        
        {error && <div className="error-message" style={{ marginBottom: '1.5rem' }}>{error}</div>}
        
        {!showAdminLogin ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center', width: '100%' }}>
            {submitting ? (
              <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>Verifying login...</div>
            ) : (
              <>
                {/* Google Sign-In */}
                <div id="google-signin-btn-login-page" style={{ minHeight: '40px' }}></div>
                
                {/* GitHub Sign-In */}
                {githubClientId && (
                  <button 
                    type="button" 
                    onClick={handleGithubLogin} 
                    className="editorial-button"
                    style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center', 
                      gap: '10px', 
                      background: '#24292e', 
                      color: '#fff', 
                      borderColor: '#24292e',
                      width: '280px',
                      margin: 0
                    }}
                  >
                    <svg height="20" width="20" viewBox="0 0 16 16" fill="currentColor">
                      <path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                    </svg>
                    Sign In with GitHub
                  </button>
                )}

                <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-color)', width: '100%', paddingTop: '1rem', textAlign: 'center' }}>
                  <button 
                    type="button" 
                    onClick={() => setShowAdminLogin(true)}
                    style={{ background: 'none', border: 'none', color: 'var(--accent-color)', cursor: 'pointer', fontSize: '0.8rem', textDecoration: 'underline' }}
                  >
                    Admin staff sign in
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="username">Username</label>
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
              <label className="form-label" htmlFor="password">Password</label>
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
                style={{ margin: 0, background: 'none', color: 'var(--text-color)', border: '1px solid var(--border-color)' }}
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
