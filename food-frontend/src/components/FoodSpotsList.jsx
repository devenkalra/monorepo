import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import RatingStars from './RatingStars';

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
              <Link
                to={`/spot/${spot.id}`}
                className="flex gap-3 p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition"
              >
                {spot.photos && spot.photos.length > 0 && (
                  <div className="flex-shrink-0 w-10 h-10 rounded overflow-hidden bg-gray-100 dark:bg-gray-700">
                    <img
                      src={spot.photos[0]?.thumbnail_url || spot.photos[0]?.url || spot.photos[0]}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <div className="flex justify-between items-center gap-2 min-w-0 flex-1">
                  <div className="min-w-0 flex-1">
                    <span className="font-medium text-gray-900 dark:text-gray-100">{spot.name}</span>
                    {(spot.food_rating_avg != null || spot.rating_avg != null) && (
                      <span className="ml-2 inline-flex items-center">
                        <RatingStars
                          value={spot.food_rating_avg ?? spot.rating_avg}
                          count={spot.food_rating_avg != null ? spot.food_rating_count : spot.rating_count}
                          size="sm"
                        />
                      </span>
                    )}
                    {spot.added_by_username && (
                      <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">added by {spot.added_by_username}</span>
                    )}
                    {spot.foods && spot.foods.length > 0 && (
                      <span className="text-sm text-gray-600 dark:text-gray-400 ml-2 flex flex-wrap gap-1">
                        {spot.foods.map((f) => (
                          <span
                            key={f.id}
                            className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                          >
                            {f.name}
                            {f.rating_avg != null && (
                              <span className="text-amber-500 dark:text-amber-400 font-medium">★{f.rating_avg}</span>
                            )}
                          </span>
                        ))}
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
