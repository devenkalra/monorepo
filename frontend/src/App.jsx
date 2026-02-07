import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Login from './components/Login';
import Register from './components/Register';
import PrivateRoute from './components/PrivateRoute';
import UserMenu from './components/UserMenu';
import SearchBar from './components/SearchBar';
import api from './services/api';

// Main app component (your entity manager)
function MainApp() {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState({});
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load entities
  useEffect(() => {
    loadEntities();
  }, []);

  const loadEntities = async () => {
    setLoading(true);
    try {
      const data = await api.getRecentEntities(20);
      setEntities(data.results || data || []);
    } catch (error) {
      console.error('Failed to load entities:', error);
    } finally {
      setLoading(false);
    }
  };

  // Search function
  const handleSearch = async () => {
    if (!query.trim()) {
      loadEntities();
      return;
    }

    setLoading(true);
    try {
      const data = await api.search(query, filters);
      setEntities(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  // Search on query/filter change
  useEffect(() => {
    const timer = setTimeout(() => {
      if (query) {
        handleSearch();
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [query, filters]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header with user menu */}
      <header className="bg-white dark:bg-gray-800 shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Entity Manager</h1>
          <UserMenu />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        <SearchBar 
          query={query} 
          setQuery={setQuery} 
          filters={filters} 
          setFilters={setFilters}
        />

        {/* Entity list */}
        <div className="mt-8">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
              <p className="mt-4 text-gray-600">Loading...</p>
            </div>
          ) : entities.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500">No entities found. Create your first entity!</p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {entities.map((entity) => (
                <div
                  key={entity.id}
                  className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="inline-block px-2 py-1 bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 text-xs font-semibold rounded">
                          {entity.type}
                        </span>
                      </div>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                        {entity.label || entity.display || 'Untitled'}
                      </h3>
                      {entity.description && (
                        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                          {entity.description}
                        </p>
                      )}
                      {entity.tags && entity.tags.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1">
                          {entity.tags.slice(0, 3).map((tag, idx) => (
                            <span
                              key={idx}
                              className="inline-block px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded"
                            >
                              {tag}
                            </span>
                          ))}
                          {entity.tags.length > 3 && (
                            <span className="text-xs text-gray-500">
                              +{entity.tags.length - 3} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick actions */}
        <div className="mt-8 flex gap-4">
          <button
            onClick={() => {/* TODO: Open create person modal */}}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            + Create Person
          </button>
          <button
            onClick={() => {/* TODO: Open create note modal */}}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
          >
            + Create Note
          </button>
        </div>
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
