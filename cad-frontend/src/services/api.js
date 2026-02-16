import { getApiBaseUrl } from '../utils/apiUrl';

const AUTH_EXPIRED_EVENT = 'auth-expired';

function getCsrfToken() {
  const name = 'csrftoken';
  if (!document.cookie) return null;
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[2]) : null;
}

/** Ensure CSRF cookie is set (call once when app loads, e.g. from /cad-app/) */
export async function ensureCsrfCookie() {
  const base = getApiBaseUrl();
  await fetch(`${base}/api/auth/csrf/`, { method: 'GET', credentials: 'include' });
}

async function tryRefreshToken() {
  const refresh = localStorage.getItem('refresh_token');
  if (!refresh) return null;
  const base = getApiBaseUrl();
  const headers = { 'Content-Type': 'application/json' };
  const csrf = getCsrfToken();
  if (csrf) headers['X-CSRFToken'] = csrf;
  const res = await fetch(`${base}/api/auth/token/refresh/`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ refresh }),
    credentials: 'include',
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (data.access) {
    localStorage.setItem('access_token', data.access);
    return data.access;
  }
  return null;
}

function dispatchAuthExpired() {
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

// Create a fetch wrapper that automatically prepends the API base URL,
// includes authentication headers, and handles 401 with token refresh
const api = {
  fetch: async (url, options = {}) => {
    const API_BASE = getApiBaseUrl();
    const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;

    const doFetch = (token) => {
      const headers = { ...options.headers };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const csrf = getCsrfToken();
      if (csrf) headers['X-CSRFToken'] = csrf;
      if (options.body && !headers['Content-Type'] && !(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }
      return fetch(fullUrl, {
        ...options,
        headers,
        credentials: options.credentials ?? 'include',
      });
    };

    let res = await doFetch(localStorage.getItem('access_token'));

    if (res.status === 401) {
      const newToken = await tryRefreshToken();
      if (newToken) {
        res = await doFetch(newToken);
      } else {
        dispatchAuthExpired();
      }
    }

    return res;
  },
};

export default api;
export { AUTH_EXPIRED_EVENT };
