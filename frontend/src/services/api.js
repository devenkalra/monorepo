const API_BASE = 'http://localhost:8001';

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

  // Entity endpoints
  async getEntities(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/entities/${queryString ? `?${queryString}` : ''}`);
  }

  async getEntity(id) {
    return this.request(`/api/entities/${id}/`);
  }

  async getRecentEntities(limit = 20) {
    return this.request(`/api/entities/recent/?limit=${limit}`);
  }

  // People endpoints
  async getPeople(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/people/${queryString ? `?${queryString}` : ''}`);
  }

  async createPerson(data) {
    return this.request('/api/people/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async updatePerson(id, data) {
    return this.request(`/api/people/${id}/`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async deletePerson(id) {
    return this.request(`/api/people/${id}/`, {
      method: 'DELETE'
    });
  }

  // Notes endpoints
  async getNotes(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/notes/${queryString ? `?${queryString}` : ''}`);
  }

  async createNote(data) {
    return this.request('/api/notes/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  // Search endpoint
  async search(query, filters = {}) {
    const params = { q: query, ...filters };
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/search/?${queryString}`);
  }

  // Conversations
  async getConversations(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/conversations/${queryString ? `?${queryString}` : ''}`);
  }
}

export const api = new ApiClient();
export default api;
