import { getApiBaseUrl } from '../utils/apiUrl';

// Create a fetch wrapper that automatically prepends the API base URL
// and includes authentication headers
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
    });
  }
};

export default api;
