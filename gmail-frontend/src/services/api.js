import { getApiBaseUrl } from '../utils/apiUrl';

const api = {
  async fetch(url, options = {}) {
    const API_BASE = getApiBaseUrl();
    const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
    const token = localStorage.getItem('access_token');
    const headers = { ...options.headers };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(fullUrl, { ...options, headers, credentials: 'include' });
    if (res.status === 401) {
      // Let the caller surface the error; AuthContext/GmailApp own login redirects.
      // Hard-navigating here races token refresh and causes login loops.
      throw new Error('Unauthorized');
    }
    return res;
  },

  async json(url, options = {}) {
    const res = await this.fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof data.detail === 'string'
          ? data.detail
          : data.detail
            ? JSON.stringify(data.detail)
            : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    return data;
  },
};

export default api;
