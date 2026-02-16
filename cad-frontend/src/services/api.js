import { getApiBaseUrl } from '../utils/apiUrl';

const AUTH_EXPIRED_EVENT = 'auth-expired';

async function tryRefreshToken() {
  const refresh = localStorage.getItem('refresh_token');
  if (!refresh) return null;
  const base = getApiBaseUrl();
  const res = await fetch(`${base}/api/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
