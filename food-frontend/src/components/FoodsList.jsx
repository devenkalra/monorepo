import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function FoodsList({ apiBase, user }) {
  const [foods, setFoods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  const loadFoods = useCallback(async () => {
    setLoading(true);
    try {
      const url = search ? `${apiBase}/foods/?search=${encodeURIComponent(search)}` : `${apiBase}/foods/`;
      const res = await api.fetch(url);
      const data = await res.json();
      setFoods(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      console.error('Failed to load foods', err);
      setFoods([]);
    } finally {
      setLoading(false);
    }
  }, [apiBase, search]);

  useEffect(() => {
    loadFoods();
  }, [loadFoods]);

  const toggleExpand = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div>
      <div className="mb-4 flex gap-2">
        <input
          type="text"
          placeholder="Search foods…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        />
        {user && (
          <Link
            to={search ? `/food/create?name=${encodeURIComponent(search)}` : '/food/create'}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium"
          >
            + Add Food
          </Link>
        )}
      </div>
      {loading ? (
        <p className="text-center text-gray-500 py-8">Loading…</p>
      ) : foods.length === 0 ? (
        <p className="text-center text-gray-500 py-8">No foods found.</p>
      ) : (
        <ul className="space-y-2">
          {foods.map((food) => (
            <li
              key={food.id}
              className="p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition"
            >
              <div
                className="flex justify-between items-center gap-2 cursor-pointer"
                onClick={() => toggleExpand(food.id)}
              >
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-gray-900 dark:text-gray-100">{food.name}</span>
                  {food.added_by_username && (
                    <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">added by {food.added_by_username}</span>
                  )}
                  {food.served_at_names && food.served_at_names.length > 0 && (
                    <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">
                      {food.served_at_names.join(', ')}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <Link
                    to={`/food/${food.id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="p-1 rounded text-gray-400 hover:text-amber-600 dark:hover:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20"
                    title="Show detail"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                      <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
                    </svg>
                  </Link>
                  <span className="text-gray-400">{expandedId === food.id ? '▼' : '▶'}</span>
                </div>
              </div>
              {expandedId === food.id && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                  <div className="max-h-40 overflow-y-auto space-y-2 text-sm">
                    {food.alsocalled && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Also called</p>
                        <p className="text-gray-700 dark:text-gray-300">{food.alsocalled}</p>
                      </div>
                    )}
                    {food.description && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Description</p>
                        <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{food.description}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
