import { getApiBaseUrl } from '../utils/apiUrl';

function formatApiError(data, status) {
  if (!data || typeof data !== 'object') return `HTTP ${status}`;
  if (typeof data.detail === 'string') return data.detail;
  if (data.detail) return JSON.stringify(data.detail);
  const parts = [];
  for (const [key, value] of Object.entries(data)) {
    if (key === 'detail') continue;
    const text = Array.isArray(value)
      ? value.map((v) => (typeof v === 'string' ? v : JSON.stringify(v))).join(' ')
      : typeof value === 'string'
        ? value
        : JSON.stringify(value);
    parts.push(key === 'non_field_errors' ? text : `${key}: ${text}`);
  }
  return parts.join(' ') || `HTTP ${status}`;
}

const api = {
  async fetch(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${getApiBaseUrl()}${url}`;
    const token = localStorage.getItem('access_token');
    const headers = { ...options.headers };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(fullUrl, { ...options, headers, credentials: 'include' });
    if (res.status === 401) throw new Error('Unauthorized');
    return res;
  },

  async json(url, options = {}) {
    const res = await this.fetch(url, options);
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(formatApiError(data, res.status));
    return data;
  },
};

export default api;
