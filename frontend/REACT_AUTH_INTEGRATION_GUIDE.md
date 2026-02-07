# React Authentication Integration Guide

## Overview

This guide shows how to integrate JWT authentication into your existing React frontend that displays and edits entities.

---

## Files to Create

```
frontend/src/
├── contexts/
│   └── AuthContext.jsx          # Authentication context & provider
├── components/
│   ├── Login.jsx                # Login form component
│   ├── Register.jsx             # Registration form component
│   ├── PrivateRoute.jsx         # Protected route wrapper
│   └── UserMenu.jsx             # User info & logout button
├── services/
│   └── api.js                   # API client with auth
└── App.jsx                      # Updated with auth routing
```

---

## Step-by-Step Integration

### 1. Install Dependencies

```bash
cd /home/ubuntu/monorepo/frontend
npm install react-router-dom jwt-decode
```

### 2. Create Authentication Context

**File:** `src/contexts/AuthContext.jsx`

```jsx
import React, { createContext, useState, useContext, useEffect } from 'react';
import { jwtDecode } from 'jwt-decode';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load user from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const userStr = localStorage.getItem('current_user');
    
    if (token && userStr) {
      // Check if token is expired
      try {
        const decoded = jwtDecode(token);
        if (decoded.exp * 1000 > Date.now()) {
          setAccessToken(token);
          setUser(JSON.parse(userStr));
        } else {
          // Token expired, try to refresh
          refreshToken();
        }
      } catch (error) {
        console.error('Invalid token:', error);
        logout();
      }
    }
    setLoading(false);
  }, []);

  const login = async (email, password) => {
    const response = await fetch('http://localhost:8001/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.non_field_errors?.[0] || error.detail || 'Login failed');
    }

    const data = await response.json();
    
    // Store tokens and user info
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    localStorage.setItem('current_user', JSON.stringify(data.user));
    
    setAccessToken(data.access);
    setUser(data.user);
    
    return data.user;
  };

  const register = async (email, password1, password2) => {
    const response = await fetch('http://localhost:8001/api/auth/registration/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password1, password2 })
    });

    if (!response.ok) {
      const error = await response.json();
      const messages = [];
      if (error.email) messages.push(...error.email);
      if (error.password1) messages.push(...error.password1);
      if (error.non_field_errors) messages.push(...error.non_field_errors);
      throw new Error(messages.join('. ') || 'Registration failed');
    }

    const data = await response.json();
    
    // Store tokens and user info
    localStorage.setItem('access_token', data.access);
    localStorage.setItem('refresh_token', data.refresh);
    localStorage.setItem('current_user', JSON.stringify(data.user));
    
    setAccessToken(data.access);
    setUser(data.user);
    
    return data.user;
  };

  const logout = async () => {
    // Call logout endpoint
    if (accessToken) {
      try {
        await fetch('http://localhost:8001/api/auth/logout/', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${accessToken}`
          }
        });
      } catch (error) {
        console.error('Logout error:', error);
      }
    }

    // Clear local storage
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
    
    setAccessToken(null);
    setUser(null);
  };

  const refreshToken = async () => {
    const refresh = localStorage.getItem('refresh_token');
    
    if (!refresh) {
      logout();
      return null;
    }

    try {
      const response = await fetch('http://localhost:8001/api/auth/token/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh })
      });

      if (!response.ok) {
        throw new Error('Refresh failed');
      }

      const data = await response.json();
      localStorage.setItem('access_token', data.access);
      setAccessToken(data.access);
      
      return data.access;
    } catch (error) {
      console.error('Token refresh failed:', error);
      logout();
      return null;
    }
  };

  const value = {
    user,
    accessToken,
    loading,
    login,
    register,
    logout,
    refreshToken,
    isAuthenticated: !!user
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
```

### 3. Create API Client

**File:** `src/services/api.js`

```javascript
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
```

### 4. Create Login Component

**File:** `src/components/Login.jsx`

```jsx
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Test user quick fill
  const quickFill = (testEmail, testPassword) => {
    setEmail(testEmail);
    setPassword(testPassword);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-600 to-purple-700 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Welcome Back</h1>
          <p className="text-gray-600">Sign in to access your entities</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        {/* Test Users */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <p className="text-sm font-medium text-blue-900 mb-2">👥 Test Users (click to fill)</p>
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => quickFill('alice@example.com', 'testpass123')}
              className="w-full text-left px-3 py-2 bg-white rounded border border-blue-300 hover:bg-blue-50 text-sm font-mono"
            >
              alice@example.com / testpass123
            </button>
            <button
              type="button"
              onClick={() => quickFill('bob@example.com', 'testpass123')}
              className="w-full text-left px-3 py-2 bg-white rounded border border-blue-300 hover:bg-blue-50 text-sm font-mono"
            >
              bob@example.com / testpass123
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              placeholder="your@email.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold py-3 px-4 rounded-lg hover:from-indigo-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-gray-600">
            Don't have an account?{' '}
            <Link to="/register" className="text-indigo-600 hover:text-indigo-700 font-semibold">
              Register
            </Link>
          </p>
        </div>

        <div className="mt-6 border-t pt-6">
          <p className="text-center text-sm text-gray-500 mb-4">Or continue with</p>
          <div className="space-y-2">
            <a
              href="http://localhost:8001/accounts/google/login/"
              className="w-full flex items-center justify-center px-4 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <span className="text-gray-700 font-medium">Google</span>
            </a>
            <a
              href="http://localhost:8001/accounts/github/login/"
              className="w-full flex items-center justify-center px-4 py-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <span className="text-gray-700 font-medium">GitHub</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
```

### 5. Create Register Component

**File:** `src/components/Register.jsx`

```jsx
import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password1, setPassword1] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password1 !== password2) {
      setError('Passwords do not match');
      return;
    }

    if (password1.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);

    try {
      await register(email, password1, password2);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-600 to-purple-700 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Create Account</h1>
          <p className="text-gray-600">Join and manage your entities</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              placeholder="your@email.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Password
            </label>
            <input
              type="password"
              value={password1}
              onChange={(e) => setPassword1(e.target.value)}
              required
              minLength={8}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Confirm Password
            </label>
            <input
              type="password"
              value={password2}
              onChange={(e) => setPassword2(e.target.value)}
              required
              minLength={8}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold py-3 px-4 rounded-lg hover:from-indigo-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? 'Creating Account...' : 'Create Account'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-gray-600">
            Already have an account?{' '}
            <Link to="/login" className="text-indigo-600 hover:text-indigo-700 font-semibold">
              Sign In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
```

### 6. Create Protected Route Component

**File:** `src/components/PrivateRoute.jsx`

```jsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function PrivateRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return isAuthenticated ? children : <Navigate to="/login" />;
}
```

### 7. Create User Menu Component

**File:** `src/components/UserMenu.jsx`

```jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function UserMenu() {
  const { user, logout } = useAuth();
  const [showMenu, setShowMenu] = useState(false);
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowMenu(!showMenu)}
        className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
      >
        <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white font-semibold">
          {user?.email?.[0]?.toUpperCase() || 'U'}
        </div>
        <span className="text-sm font-medium">{user?.email}</span>
      </button>

      {showMenu && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowMenu(false)}
          />
          <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg z-20 border border-gray-200 dark:border-gray-700">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
              <p className="text-sm font-semibold">{user?.username || 'User'}</p>
              <p className="text-xs text-gray-500">{user?.email}</p>
            </div>
            <button
              onClick={handleLogout}
              className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-b-lg"
            >
              Logout
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

### 8. Update App.jsx with Routing

**File:** `src/App.jsx`

```jsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import Login from './components/Login';
import Register from './components/Register';
import PrivateRoute from './components/PrivateRoute';
import UserMenu from './components/UserMenu';
import SearchBar from './components/SearchBar';

// Your main app component (entities list/edit)
function MainApp() {
  // ... your existing entity management code
  // Now uses authenticated API calls via api.js
  
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header with user menu */}
      <header className="bg-white dark:bg-gray-800 shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold">Entity Manager</h1>
          <UserMenu />
        </div>
      </header>

      {/* Your existing app content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        <SearchBar /* ... */ />
        {/* Entity list, forms, etc. */}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/*"
            element={
              <PrivateRoute>
                <MainApp />
              </PrivateRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
```

### 9. Update SearchBar to Use API Client

**File:** `src/components/SearchBar.jsx` (update line 79)

```javascript
// Change from:
const resp = await fetch(`/api/search/?q=${encodeURIComponent(searchText)}&limit=5`);

// To:
import api from '../services/api';
const data = await api.search(searchText, { limit: 5 });
```

---

## Quick Start

```bash
cd /home/ubuntu/monorepo/frontend

# Install dependencies
npm install react-router-dom jwt-decode

# Create directories
mkdir -p src/contexts src/services

# Copy the files above into their respective locations

# Start dev server
npm start
```

---

## Testing

1. **Open:** http://localhost:3000/
2. **Should redirect to:** /login
3. **Click test user:** alice@example.com
4. **Login**
5. **See main app** with SearchBar and entities
6. **Try creating entities** - they're auto-assigned to Alice
7. **Logout and login as Bob** - see different data!

---

## Benefits

✅ **Seamless Integration** - Works with your existing SearchBar and components  
✅ **Automatic Token Management** - Handles refresh automatically  
✅ **Protected Routes** - Unauthenticated users can't access entities  
✅ **User Context** - Easy access to current user everywhere  
✅ **Clean API** - Single `api` client for all backend calls  
✅ **Social Auth Ready** - Google/GitHub login included  

---

## Next Steps

1. Update all your fetch calls to use the `api` client
2. Add entity creation/editing forms
3. Show user-specific data throughout the app
4. Add profile management
5. Deploy to production with your backend

Your frontend is now a complete multi-user application! 🎉
