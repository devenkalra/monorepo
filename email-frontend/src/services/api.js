const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  if (typeof window !== 'undefined') {
    const { protocol, hostname, port } = window.location;
    // If running through nginx (port 80 or 443), use same origin for proxy
    if (port === '80' || port === '443' || port === '') {
      return '';
    }
    // If running on dev server (5176), connect to backend directly
    if (port === '5176') {
      return `${protocol}//${hostname}:8000`;
    }
    return `${protocol}//${hostname}`;
  }
  
  return '';
};

const api = {
  fetch: (url, options = {}) => {
    const API_BASE = getApiBaseUrl();
    const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;
    
    const token = localStorage.getItem('access_token');
    
    const headers = {
      ...options.headers,
    };
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    if (options.body && !headers['Content-Type']) {
      if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }
    }
    
    return fetch(fullUrl, {
      ...options,
      headers,
    });
  }
};

export default api;
