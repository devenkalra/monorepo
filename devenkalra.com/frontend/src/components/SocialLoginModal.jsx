import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

export const SocialLoginModal = () => {
  const { 
    isSocialLoginModalOpen, 
    closeSocialLoginModal, 
    loginWithGoogle, 
    socialLoginCallback 
  } = useAuth();

  const [googleClientId, setGoogleClientId] = useState('');
  const [githubClientId, setGithubClientId] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isSocialLoginModalOpen) return;
    
    // Fetch configuration
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
  }, [isSocialLoginModalOpen]);

  // Load Google accounts GSI script on demand
  useEffect(() => {
    if (!isSocialLoginModalOpen || !googleClientId) return;

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = () => {
      if (window.google) {
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            setLoading(true);
            setLoginError('');
            const res = await loginWithGoogle(response.credential);
            setLoading(false);
            if (res.success) {
              closeSocialLoginModal();
              if (socialLoginCallback) {
                socialLoginCallback();
              }
            } else {
              setLoginError(res.error || 'Failed to sign in with Google.');
            }
          }
        });
        window.google.accounts.id.renderButton(
          document.getElementById('google-signin-btn-modal'),
          { theme: 'outline', size: 'large', width: 280 }
        );
      }
    };
    document.body.appendChild(script);
    return () => {
      try { document.body.removeChild(script); } catch (e) {}
    };
  }, [isSocialLoginModalOpen, googleClientId, loginWithGoogle, closeSocialLoginModal, socialLoginCallback]);

  const handleGithubLogin = () => {
    if (!githubClientId) return;
    localStorage.setItem('authRedirectPath', window.location.pathname + window.location.search);
    const redirectUri = window.location.origin + '/login/github/callback';
    const authUrl = `https://github.com/login/oauth/authorize?client_id=${githubClientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=user%3Aemail`;
    window.location.href = authUrl;
  };

  if (!isSocialLoginModalOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.45)',
      backdropFilter: 'blur(8px)',
      WebkitBackdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10000,
      animation: 'fadeIn 0.2s ease-out'
    }}>
      <div style={{
        backgroundColor: 'var(--bg-color, #ffffff)',
        border: '1px solid var(--border-dark, #e0dcd3)',
        borderRadius: '8px',
        padding: '2.5rem',
        maxWidth: '420px',
        width: '90%',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        position: 'relative',
        animation: 'slideUp 0.25s ease-out'
      }}>
        {/* Close Button */}
        <button 
          onClick={closeSocialLoginModal}
          style={{
            position: 'absolute',
            top: '1rem',
            right: '1rem',
            background: 'none',
            border: 'none',
            fontSize: '1.25rem',
            cursor: 'pointer',
            color: 'var(--text-muted, #7f8c8d)',
            padding: '0.25rem 0.5rem'
          }}
          aria-label="Close modal"
        >
          ✕
        </button>

        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>✨</div>
          <h3 style={{ fontSize: '1.6rem', fontFamily: 'var(--font-serif)', margin: '0 0 0.5rem 0', fontWeight: '500' }}>
            Social Sign In
          </h3>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-muted, #7f8c8d)', margin: 0, lineHeight: '1.5' }}>
            Authenticate temporarily using a social account to access pages and subscribe to updates. No account creation required.
          </p>
        </div>

        {loginError && (
          <div className="error-message" style={{ marginBottom: '1.5rem', fontSize: '0.85rem' }}>
            ✕ {loginError}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center', width: '100%' }}>
          {loading ? (
            <div style={{ padding: '1.5rem', color: 'var(--text-muted)' }}>
              Verifying login session...
            </div>
          ) : (
            <>
              {/* Google Button */}
              <div id="google-signin-btn-modal" style={{ minHeight: '40px' }}></div>
              
              {/* GitHub Button */}
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
            </>
          )}
        </div>
      </div>
    </div>
  );
};
