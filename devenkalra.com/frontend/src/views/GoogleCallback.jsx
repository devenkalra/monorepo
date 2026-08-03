import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { consumeGoogleOAuthState, getGoogleRedirectUri } from '../utils/googleOAuth';

export const GoogleCallback = () => {
  const [searchParams] = useSearchParams();
  const { loginWithGoogleCode } = useAuth();
  const navigate = useNavigate();
  const [statusText, setStatusText] = useState('Authenticating with Google...');
  const [error, setError] = useState('');

  useEffect(() => {
    const oauthError = searchParams.get('error');
    if (oauthError) {
      setError(searchParams.get('error_description') || `Google returned an error: ${oauthError}`);
      return;
    }

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    if (!code) {
      setError('Google authentication code is missing.');
      return;
    }
    if (!consumeGoogleOAuthState(state)) {
      setError('Google login state mismatch. Please try signing in again.');
      return;
    }

    let cancelled = false;
    (async () => {
      const result = await loginWithGoogleCode(code, getGoogleRedirectUri());
      if (cancelled) return;
      if (result.success) {
        setStatusText('Success! Redirecting...');
        const nextPath = localStorage.getItem('authRedirectPath') || '/';
        localStorage.removeItem('authRedirectPath');
        navigate(nextPath, { replace: true });
      } else {
        setError(result.error || 'Failed to authenticate with Google.');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [searchParams, loginWithGoogleCode, navigate]);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '6rem 2rem' }}>
      <div
        className="auth-card"
        style={{ boxShadow: 'none', border: '1px solid var(--border-dark)', textAlign: 'center' }}
      >
        {error ? (
          <>
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: '#e74c3c' }}>❌</div>
            <h2>Authentication Failed</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>{error}</p>
            <button onClick={() => navigate('/login')} className="editorial-button">
              Back to Sign In
            </button>
          </>
        ) : (
          <>
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: 'var(--accent-color)' }}>
              ⏳
            </div>
            <h2>Google Authentication</h2>
            <p style={{ color: 'var(--text-muted)' }}>{statusText}</p>
          </>
        )}
      </div>
    </div>
  );
};
