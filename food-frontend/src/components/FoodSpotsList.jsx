import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import SpotCard from './SpotCard';

export default function FoodSpotsList({ apiBase, user }) {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const loadSpots = useCallback(async () => {
    setLoading(true);
    try {
      const url = search ? `${apiBase}/spots/?search=${encodeURIComponent(search)}` : `${apiBase}/spots/`;
      const res = await api.fetch(url);
      const data = await res.json();
      setSpots(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      console.error('Failed to load food spots', err);
      setSpots([]);
    } finally {
      setLoading(false);
    }
  }, [apiBase, search]);

  useEffect(() => {
    loadSpots();
  }, [loadSpots]);

  return (
    <div>
      <div className="mb-4 flex gap-2">
        <input
          type="text"
          placeholder="Search spots…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        />
        {user && (
          <Link
            to="/spot/create"
            className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium"
          >
            + Add Spot
          </Link>
        )}
      </div>
      {loading ? (
        <p className="text-center text-gray-500 py-8">Loading…</p>
      ) : spots.length === 0 ? (
        <p className="text-center text-gray-500 py-8">No food spots found.</p>
      ) : (
        <ul className="space-y-2">
          {spots.map((spot) => (
            <li key={spot.id}>
              <SpotCard spot={spot} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
