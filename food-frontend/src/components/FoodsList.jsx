import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import FoodCard from './FoodCard';

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
              <FoodCard food={food} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
