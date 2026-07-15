import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const GithubCallback = () => {
  const [searchParams] = useSearchParams();
  const { loginWithGithub } = useAuth();
  const navigate = useNavigate();
  const [statusText, setStatusText] = useState('Authenticating with GitHub...');
  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setError('GitHub authentication code is missing.');
      return;
    }

    const performLogin = async () => {
      const result = await loginWithGithub(code);
      if (result.success) {
        setStatusText('Success! Redirecting...');
        const nextPath = localStorage.getItem('authRedirectPath') || '/';
        localStorage.removeItem('authRedirectPath');
        navigate(nextPath);
      } else {
        setError(result.error || 'Failed to authenticate with GitHub.');
      }
    };

    performLogin();
  }, [searchParams, loginWithGithub, navigate]);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '6rem 2rem' }}>
      <div className="auth-card" style={{ boxShadow: 'none', border: '1px solid var(--border-dark)', textAlign: 'center' }}>
        {error ? (
          <>
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: '#e74c3c' }}>❌</div>
            <h2>Authentication Failed</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>{error}</p>
            <button onClick={() => navigate('/')} className="editorial-button">
              Return to Home
            </button>
          </>
        ) : (
          <>
            <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: 'var(--accent-color)' }}>⏳</div>
            <h2>GitHub Authentication</h2>
            <p style={{ color: 'var(--text-muted)' }}>{statusText}</p>
          </>
        )}
      </div>
    </div>
  );
};
