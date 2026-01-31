const API_BASE = 'http://localhost:8000';

class ApiClient {
  constructor() {
    this.baseURL = API_BASE;
  }

  getAccessToken() {
    return localStorage.getItem('access_token');
  }

  async refreshToken() {
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) throw new Error('No refresh token');

    const response = await fetch(`${this.baseURL}/api/auth/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh })
    });

    if (!response.ok) throw new Error('Token refresh failed');

    const data = await response.json();
    localStorage.setItem('access_token', data.access);
    return data.access;
  }

  async request(endpoint, options = {}) {
    const token = this.getAccessToken();
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    let response = await fetch(`${this.baseURL}${endpoint}`, {
      ...options,
      headers
    });

    // If 401, try to refresh token and retry once
    if (response.status === 401 && token) {
      try {
        const newToken = await this.refreshToken();
        headers['Authorization'] = `Bearer ${newToken}`;
        
        response = await fetch(`${this.baseURL}${endpoint}`, {
          ...options,
          headers
        });
      } catch (error) {
        // Refresh failed, redirect to login
        localStorage.clear();
        window.location.href = '/login';
        throw error;
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `API Error: ${response.status}`);
    }

    return response.json();
  }

  // Helper to make authenticated fetch with same interface as native fetch
  async fetch(url, options = {}) {
    const token = this.getAccessToken();
    
    // Prepend base URL if the URL is relative (starts with /)
    const fullUrl = url.startsWith('/') ? `${this.baseURL}${url}` : url;
    
    const headers = {
      ...options.headers
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    let response = await fetch(fullUrl, {
      ...options,
      headers
    });

    // If 401, try to refresh token and retry once
    if (response.status === 401 && token) {
      try {
        const newToken = await this.refreshToken();
        headers['Authorization'] = `Bearer ${newToken}`;
        
        response = await fetch(fullUrl, {
          ...options,
          headers
        });
      } catch (error) {
        // Refresh failed, redirect to login
        localStorage.clear();
        window.location.href = '/login';
        throw error;
      }
    }

    return response;
  }
}

export const api = new ApiClient();
export default api;
