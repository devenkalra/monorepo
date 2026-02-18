import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import MediaSection from './MediaSection';
import YouTubeSection from './YouTubeSection';

export default function FoodSpotDetail({ apiBase, user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [spot, setSpot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [descCollapsed, setDescCollapsed] = useState(true);
  const [selectedFoodId, setSelectedFoodId] = useState(null);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      try {
        const res = await api.fetch(`${apiBase}/spots/${id}/`);
        const data = await res.json();
        setSpot(data);
      } catch (err) {
        console.error('Failed to load food spot', err);
        setSpot(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [apiBase, id]);

  if (loading) return <p className="text-center text-gray-500 py-8">Loading…</p>;
  if (!spot) return <p className="text-center text-gray-500 py-8">Not found.</p>;

  const canEdit = user && spot.added_by === (user.id ?? user.pk);

  const selectedFood = spot.foods?.find((f) => f.id === selectedFoodId);

  return (
    <div>
      <div className="mb-4">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-amber-600 dark:text-amber-400 hover:underline"
        >
          ← Back
        </button>
      </div>
      <div className="flex justify-between items-start mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{spot.name}</h1>
        {canEdit && (
          <Link
            to={`/spot/${id}/edit`}
            className="text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline"
          >
            Edit
          </Link>
        )}
      </div>
      {spot.location && (
        <p className="text-gray-600 dark:text-gray-400 mb-4">{spot.location}</p>
      )}
      {spot.tags && spot.tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {spot.tags.map((tag, idx) => (
            <span
              key={idx}
              className="inline-flex px-3 py-1 bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 rounded-full text-sm"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {spot.photos && spot.photos.length > 0 && (
        <div className="mb-4">
          <MediaSection photos={spot.photos} readOnly />
        </div>
      )}

      {spot.urls && spot.urls.length > 0 && (
        <div className="mb-4">
          <YouTubeSection urls={spot.urls} readOnly />
        </div>
      )}

      {spot.description && (
        <div className="mb-4">
          <button
            onClick={() => setDescCollapsed(!descCollapsed)}
            className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300"
          >
            Description {descCollapsed ? '▶' : '▼'}
          </button>
          {!descCollapsed && (
            <div className="mt-2 p-3 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800">
              {spot.description}
            </div>
          )}
        </div>
      )}

      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Foods</h2>
      {spot.foods && spot.foods.length > 0 ? (
        <div className="space-y-2">
          {spot.foods.map((f) => (
            <div
              key={f.id}
              className="p-3 rounded-lg bg-white dark:bg-gray-800 shadow cursor-pointer hover:shadow-md"
              onClick={() => setSelectedFoodId(selectedFoodId === f.id ? null : f.id)}
            >
              <div className="flex justify-between items-center">
                <span className="font-medium text-gray-900 dark:text-gray-100">{f.name}</span>
                <span className="text-gray-400">{selectedFoodId === f.id ? '▼' : '▶'}</span>
              </div>
              {selectedFoodId === f.id && f.description && (
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{f.description}</p>
              )}
              {selectedFoodId === f.id && (
                <Link
                  to={`/food/${f.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="inline-block mt-2 text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline"
                >
                  Show Detail
                </Link>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-500">No foods listed.</p>
      )}
    </div>
  );
}
