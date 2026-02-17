import { getApiBaseUrl } from '../utils/apiUrl';

function getCsrfToken() {
  const name = 'csrftoken';
  if (!document.cookie) return null;
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[2]) : null;
}

/** Ensure CSRF cookie is set (call once when app loads) */
export async function ensureCsrfCookie() {
  const base = getApiBaseUrl();
  await fetch(`${base}/api/auth/csrf/`, { method: 'GET', credentials: 'include' });
}

// Create a fetch wrapper that automatically prepends the API base URL
// and includes authentication headers + CSRF token
const api = {
  fetch: (url, options = {}) => {
    const API_BASE = getApiBaseUrl();
    const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
    
    // Get the access token from localStorage
    const token = localStorage.getItem('access_token');
    
    // Merge headers with authentication
    const headers = {
      ...options.headers,
    };
    
    // Add Authorization header if token exists
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    // Add CSRF token for state-changing requests
    const csrf = getCsrfToken();
    if (csrf) {
      headers['X-CSRFToken'] = csrf;
    }
    
    // Add Content-Type if not already set and body is present
    if (options.body && !headers['Content-Type']) {
      // Only add Content-Type for non-FormData bodies
      if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }
    }
    
    return fetch(fullUrl, {
      ...options,
      headers,
      credentials: options.credentials ?? 'include',
    });
  }
};

export default api;
