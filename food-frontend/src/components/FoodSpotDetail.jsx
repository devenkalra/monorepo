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
  const [deleting, setDeleting] = useState(false);

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

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${spot.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api.fetch(`${apiBase}/spots/${id}/`, { method: 'DELETE' });
      navigate('/');
    } catch (err) {
      console.error('Failed to delete', err);
      alert('Failed to delete.');
    } finally {
      setDeleting(false);
    }
  };

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
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{spot.name}</h1>
          {spot.added_by_username && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">added by {spot.added_by_username}</p>
          )}
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <Link
              to={`/spot/${id}/edit`}
              className="text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline"
            >
              Edit
            </Link>
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              className="text-sm font-medium text-red-600 dark:text-red-400 hover:underline disabled:opacity-50"
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        )}
      </div>
      {spot.locations && spot.locations.length > 0 && (
        <div className="mb-4 space-y-3">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Locations</h3>
          {spot.locations.map((loc, idx) => {
            const parts = [loc.street, loc.city, loc.state, loc.country, loc.postal_code].filter(Boolean);
            const addr = parts.join(', ');
            return (
              <div key={idx} className="p-3 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
                {addr && <p className="text-gray-700 dark:text-gray-300">{addr}</p>}
                {loc.phone && (
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    <a href={`tel:${loc.phone}`} className="hover:underline">{loc.phone}</a>
                  </p>
                )}
              </div>
            );
          })}
        </div>
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

      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Foods</h2>
        {spot.foods && spot.foods.length > 0 ? (
          <>
            <div className="flex flex-wrap gap-2">
              {spot.foods.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setSelectedFoodId(selectedFoodId === f.id ? null : f.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                    selectedFoodId === f.id
                      ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 ring-1 ring-amber-300 dark:ring-amber-700'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {f.name}
                </button>
              ))}
            </div>
            {selectedFoodId && (() => {
              const food = spot.foods.find((f) => f.id === selectedFoodId);
              if (!food) return null;
              return (
                <div className="mt-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
                  {food.added_by_username && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">added by {food.added_by_username}</p>
                  )}
                  {food.alsocalled && (
                    <div className="mb-2">
                      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Also called</p>
                      <p className="text-sm text-gray-700 dark:text-gray-300">{food.alsocalled}</p>
                    </div>
                  )}
                  {food.description && (
                    <div className="mb-2">
                      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Description</p>
                      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{food.description}</p>
                    </div>
                  )}
                  {food.served_at_names && food.served_at_names.length > 0 && (
                    <div className="mb-2">
                      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-0.5">Served at</p>
                      <p className="text-sm text-gray-700 dark:text-gray-300">{food.served_at_names.join(', ')}</p>
                    </div>
                  )}
                  <Link
                    to={`/food/${food.id}`}
                    className="inline-flex items-center gap-1 text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                      <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
                    </svg>
                    Show detail
                  </Link>
                </div>
              );
            })()}
          </>
        ) : (
          <p className="text-gray-500">No foods listed.</p>
        )}
      </div>
    </div>
  );
}
