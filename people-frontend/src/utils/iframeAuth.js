/**
 * When People app runs in an iframe, it may not have access to the parent's localStorage.
 * Request auth tokens from the parent.
 */
const AUTH_MESSAGE_TYPE = 'bldrdojo-auth-token';

export function initIframeAuth() {
  if (typeof window === 'undefined') return;

  const hasToken = () => !!localStorage.getItem('access_token');

  const requestTokenFromParent = () => {
    if (window.parent !== window.self && !hasToken()) {
      window.parent.postMessage({ type: 'bldrdojo-app-ready' }, window.location.origin);
    }
  };

  const handleMessage = (event) => {
    if (event.origin !== window.location.origin) return;
    if (event.data?.type !== AUTH_MESSAGE_TYPE) return;

    const { access_token, refresh_token, user } = event.data;
    if (access_token) {
      localStorage.setItem('access_token', access_token);
      if (refresh_token) localStorage.setItem('refresh_token', refresh_token);
      if (user) localStorage.setItem('current_user', user);
    }
  };

  window.addEventListener('message', handleMessage);
  requestTokenFromParent();

  if (!hasToken() && window.parent !== window.self) {
    let attempts = 0;
    const retry = () => {
      if (!hasToken() && attempts < 10) {
        attempts++;
        requestTokenFromParent();
        setTimeout(retry, 200);
      }
    };
    setTimeout(retry, 100);
  }
}

export function waitForToken() {
  return new Promise((resolve) => {
    if (localStorage.getItem('access_token')) {
      resolve();
      return;
    }
    if (window.self === window.top) {
      resolve();
      return;
    }
    const check = () => {
      if (localStorage.getItem('access_token')) {
        resolve();
        return;
      }
      setTimeout(check, 50);
    };
    setTimeout(check, 100);
    setTimeout(resolve, 2500);
  });
}
