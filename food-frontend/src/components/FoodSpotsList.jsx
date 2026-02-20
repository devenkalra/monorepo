import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import RatingStars from './RatingStars';

export default function FoodSpotsList({ apiBase, user }) {
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
            <li
              key={spot.id}
              className="p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition"
            >
              <div
                className="flex justify-between items-center gap-2 cursor-pointer"
                onClick={() => toggleExpand(spot.id)}
              >
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-gray-900 dark:text-gray-100">{spot.name}</span>
                  {spot.rating_avg != null && (
                    <span className="ml-2 inline-flex items-center">
                      <RatingStars value={spot.rating_avg} count={spot.rating_count} size="sm" />
                    </span>
                  )}
                  {spot.added_by_username && (
                    <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">added by {spot.added_by_username}</span>
                  )}
                  {spot.foods && spot.foods.length > 0 && (
                    <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">
                      {spot.foods.map((f) => f.name).join(', ')}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <Link
                    to={`/spot/${spot.id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="p-1 rounded text-gray-400 hover:text-amber-600 dark:hover:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20"
                    title="Show detail"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                      <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
                    </svg>
                  </Link>
                  <span className="text-gray-400">{expandedId === spot.id ? '▼' : '▶'}</span>
                </div>
              </div>
              {expandedId === spot.id && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                  <div className="max-h-40 overflow-y-auto space-y-2 text-sm">
                    {spot.locations && spot.locations.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Location</p>
                        <p className="text-gray-700 dark:text-gray-300">
                          {spot.locations.map((loc) => {
                            const parts = [loc.street, loc.city, loc.state, loc.country].filter(Boolean);
                            return parts.join(', ');
                          }).filter(Boolean).join(' • ')}
                        </p>
                      </div>
                    )}
                    {spot.description && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Description</p>
                        <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{spot.description}</p>
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
