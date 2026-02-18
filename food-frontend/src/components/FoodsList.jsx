import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function FoodsList({ apiBase }) {
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
        <Link
          to={search ? `/food/create?name=${encodeURIComponent(search)}` : '/food/create'}
          className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium"
        >
          + Add Food
        </Link>
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
                className="flex justify-between items-start cursor-pointer"
                onClick={() => toggleExpand(food.id)}
              >
                <div>
                  <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">{food.name}</h2>
                  {food.alsocalled && (
                    <p className="text-sm text-gray-600 dark:text-gray-400">Also called: {food.alsocalled}</p>
                  )}
                  {food.tags && food.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {food.tags.slice(0, 5).map((tag, idx) => (
                        <span key={idx} className="text-xs px-2 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 rounded">
                          {tag}
                        </span>
                      ))}
                      {food.tags.length > 5 && (
                        <span className="text-xs text-gray-500">+{food.tags.length - 5}</span>
                      )}
                    </div>
                  )}
                </div>
                <span className="text-gray-400">
                  {expandedId === food.id ? '▼' : '▶'}
                </span>
              </div>
              {expandedId === food.id && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                  {food.description && (
                    <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">{food.description}</p>
                  )}
                  {food.served_at_names && food.served_at_names.length > 0 && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                      Served at: {food.served_at_names.join(', ')}
                    </p>
                  )}
                  <Link
                    to={`/food/${food.id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline"
                  >
                    Show Detail
                  </Link>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
