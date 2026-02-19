import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function SpotListsList({ apiBase }) {
  const [lists, setLists] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadLists = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.fetch(`${apiBase}/spot-lists/`);
      const data = await res.json();
      setLists(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      console.error('Failed to load spot lists', err);
      setLists([]);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    loadLists();
  }, [loadLists]);

  const handleDelete = async (e, listId) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm('Delete this list?')) return;
    try {
      await api.fetch(`${apiBase}/spot-lists/${listId}/`, { method: 'DELETE' });
      loadLists();
    } catch (err) {
      console.error('Failed to delete', err);
      alert('Failed to delete.');
    }
  };

  return (
    <div>
      <div className="mb-4 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Spot Lists</h2>
        <Link
          to="/spot-lists/create"
          className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium text-sm"
        >
          + New List
        </Link>
      </div>
      {loading ? (
        <p className="text-center text-gray-500 py-8">Loading…</p>
      ) : lists.length === 0 ? (
        <p className="text-center text-gray-500 py-8">No lists yet. Create one to get started.</p>
      ) : (
        <ul className="space-y-2">
          {lists.map((list) => (
            <li key={list.id}>
              <Link
                to={`/spot-lists/${list.id}`}
                className="block p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition"
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-medium text-gray-900 dark:text-gray-100">{list.name}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {list.spots?.length || 0} spots
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Link
                      to={`/spot-lists/${list.id}/edit`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-sm text-amber-600 dark:text-amber-400 hover:underline"
                    >
                      Edit
                    </Link>
                    <button
                      type="button"
                      onClick={(e) => handleDelete(e, list.id)}
                      className="text-sm text-red-600 dark:text-red-400 hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
