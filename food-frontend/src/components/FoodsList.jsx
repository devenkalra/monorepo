import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import RatingStars from './RatingStars';

export default function FoodsList({ apiBase, user }) {
  const [foods, setFoods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

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
            <li key={food.id}>
              <Link
                to={`/food/${food.id}`}
                className="flex gap-3 p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition"
              >
                {food.photos && food.photos.length > 0 && (
                  <div className="flex-shrink-0 w-10 h-10 rounded overflow-hidden bg-gray-100 dark:bg-gray-700">
                    <img
                      src={food.photos[0]?.thumbnail_url || food.photos[0]?.url || food.photos[0]}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <div className="flex justify-between items-center gap-2 min-w-0 flex-1">
                  <div className="min-w-0 flex-1">
                    <span className="font-medium text-gray-900 dark:text-gray-100">{food.name}</span>
                    {food.rating_avg != null && (
                      <span className="ml-2 inline-flex items-center">
                        <RatingStars value={food.rating_avg} count={food.rating_count} size="sm" />
                      </span>
                    )}
                    {food.added_by_username && (
                      <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">added by {food.added_by_username}</span>
                    )}
                    {food.served_at_names && food.served_at_names.length > 0 && (
                      <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">
                        {food.served_at_names.join(', ')}
                      </span>
                    )}
                  </div>
                  <span className="text-gray-400 flex-shrink-0">→</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
