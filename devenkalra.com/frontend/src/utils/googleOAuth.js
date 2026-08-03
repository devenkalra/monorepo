/**
 * Google OAuth authorization-code full-page redirect.
 * Requires Authorized redirect URI:
 *   {origin}/login/google/callback
 */

export const GOOGLE_CALLBACK_PATH = '/login/google/callback';
const OAUTH_STATE_KEY = 'googleOAuthState';

export function getGoogleRedirectUri() {
  return `${window.location.origin}${GOOGLE_CALLBACK_PATH}`;
}

export function startGoogleOAuthRedirect({ clientId, returnPath }) {
  if (!clientId) return;

  const redirectUri = getGoogleRedirectUri();
  const state =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  sessionStorage.setItem(OAUTH_STATE_KEY, state);
  if (returnPath) {
    localStorage.setItem('authRedirectPath', returnPath);
  }

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: 'openid email profile',
    access_type: 'online',
    include_granted_scopes: 'true',
    state,
    prompt: 'select_account',
  });

  window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export function consumeGoogleOAuthState(returnedState) {
  const expected = sessionStorage.getItem(OAUTH_STATE_KEY);
  sessionStorage.removeItem(OAUTH_STATE_KEY);
  if (!returnedState || !expected || returnedState !== expected) {
    return false;
  }
  return true;
}
