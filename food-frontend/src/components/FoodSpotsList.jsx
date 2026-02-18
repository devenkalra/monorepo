import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function FoodSpotsList({ apiBase }) {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState(null);

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

  const toggleExpand = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

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
        <Link
          to="/spot/create"
          className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 font-medium"
        >
          + Add Spot
        </Link>
      </div>
      {loading ? (
        <p className="text-center text-gray-500 py-8">Loading…</p>
      ) : spots.length === 0 ? (
        <p className="text-center text-gray-500 py-8">No food spots found.</p>
      ) : (
        <ul className="space-y-2">
          {spots.map((spot) => (
            <li
              key={spot.id}
              className="p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition"
            >
              <div
                className="flex justify-between items-start cursor-pointer"
                onClick={() => toggleExpand(spot.id)}
              >
                <div>
                  <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">{spot.name}</h2>
                  {spot.locations && spot.locations.length > 0 && (
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {spot.locations.map((loc) => {
                        const parts = [loc.street, loc.city, loc.state].filter(Boolean);
                        return parts.join(', ');
                      }).filter(Boolean).join(' • ')}
                    </p>
                  )}
                  {spot.tags && spot.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {spot.tags.slice(0, 5).map((tag, idx) => (
                        <span key={idx} className="text-xs px-2 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 rounded">
                          {tag}
                        </span>
                      ))}
                      {spot.tags.length > 5 && (
                        <span className="text-xs text-gray-500">+{spot.tags.length - 5}</span>
                      )}
                    </div>
                  )}
                </div>
                <span className="text-gray-400">
                  {expandedId === spot.id ? '▼' : '▶'}
                </span>
              </div>
              {expandedId === spot.id && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                  {spot.description && (
                    <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">{spot.description}</p>
                  )}
                  {spot.foods && spot.foods.length > 0 && (
                    <div className="mb-3">
                      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">Foods served:</p>
                      <ul className="space-y-1">
                        {spot.foods.map((f) => (
                          <li key={f.id} className="text-sm text-gray-700 dark:text-gray-300">
                            {f.name}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <Link
                    to={`/spot/${spot.id}`}
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
