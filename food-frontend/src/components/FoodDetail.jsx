import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import MediaSection from './MediaSection';
import YouTubeSection from './YouTubeSection';
import RatingStars from './RatingStars';
import FoodReviewForm from './FoodReviewForm';

export default function FoodDetail({ apiBase, user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [food, setFood] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSpotId, setSelectedSpotId] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const loadFood = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.fetch(`${apiBase}/foods/${id}/`);
      const data = await res.json();
      setFood(data);
    } catch (err) {
      console.error('Failed to load food', err);
      setFood(null);
    } finally {
      setLoading(false);
    }
  }, [apiBase, id]);

  useEffect(() => {
    loadFood();
  }, [loadFood]);

  if (loading) return <p className="text-center text-gray-500 py-8">Loading…</p>;
  if (!food) return <p className="text-center text-gray-500 py-8">Not found.</p>;

  const canEdit = user && food.added_by === (user.id ?? user.pk);

  const rateFoodAtSpot = async (spotId, rating, note = '') => {
    if (!user) return;
    try {
      await api.fetch(`${apiBase}/food-spot-ratings/`, {
        method: 'POST',
        body: JSON.stringify({ food: id, food_spot: spotId, rating, note }),
        headers: { 'Content-Type': 'application/json' },
      });
      loadFood();
    } catch (err) {
      console.error('Failed to rate food at spot', err);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${food.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api.fetch(`${apiBase}/foods/${id}/`, { method: 'DELETE' });
      navigate('/foods');
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{food.name}</h1>
          {food.added_by_username && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">added by {food.added_by_username}</p>
          )}
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <Link
              to={`/food/${id}/edit`}
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
      {food.alsocalled && (
        <p className="text-gray-600 dark:text-gray-400 mb-4">Also called: {food.alsocalled}</p>
      )}
      {food.tags && food.tags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {food.tags.map((tag, idx) => (
            <span
              key={idx}
              className="inline-flex px-3 py-1 bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 rounded-full text-sm"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
      {food.photos && food.photos.length > 0 && (
        <div className="mb-4">
          <MediaSection photos={food.photos} readOnly />
        </div>
      )}
      {food.urls && food.urls.length > 0 && (
        <div className="mb-4">
          <YouTubeSection urls={food.urls} readOnly />
        </div>
      )}
      {food.description && (
        <div className="mb-4 p-3 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800">
          <p className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Description</p>
          <p className="text-gray-700 dark:text-gray-300">{food.description}</p>
        </div>
      )}
      {food.served_at && food.served_at.length > 0 && (
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Served at</h2>
          {user && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Click a spot to add or view reviews for this food there.</p>
          )}
          <div className="flex flex-wrap gap-2">
            {food.served_at.map((s) => (
              <div key={s.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedSpotId(selectedSpotId === s.id ? null : s.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1 ${
                    selectedSpotId === s.id
                      ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 ring-1 ring-amber-300 dark:ring-amber-700'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {s.name}
                  <span className="text-xs opacity-70">{selectedSpotId === s.id ? '▲' : '▼'}</span>
                </button>
                {(s.rating_avg != null || s.my_rating != null || user) && (
                  <div className="flex flex-col gap-0.5 text-sm">
                    {s.rating_avg != null && (
                      <div className="flex items-center gap-2">
                        <span className="w-8 text-gray-500 dark:text-gray-400">Avg</span>
                        <RatingStars value={s.rating_avg} count={s.rating_count} size="sm" />
                      </div>
                    )}
                    {user && (
                      <div className="flex items-center gap-2">
                        <span className="w-8 text-gray-500 dark:text-gray-400">My</span>
                        <RatingStars
                          value={s.my_rating}
                          interactive
                          onRate={(r) => rateFoodAtSpot(s.id, r, s.my_review || '')}
                          size="sm"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          {selectedSpotId && (() => {
            const spot = food.served_at.find((s) => s.id === selectedSpotId);
            if (!spot) return null;
            return (
              <div className="mt-3 p-3 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
                {(spot.rating_avg != null || spot.my_rating != null || user) && (
                  <div className="mb-2 flex flex-col gap-0.5">
                    {spot.rating_avg != null && (
                      <div className="flex items-center gap-2">
                        <span className="w-16 text-xs font-semibold text-gray-500 dark:text-gray-400">Avg</span>
                        <RatingStars value={spot.rating_avg} count={spot.rating_count} size="sm" />
                      </div>
                    )}
                    {user && (
                      <div className="flex items-center gap-2">
                        <span className="w-8 text-xs font-semibold text-gray-500 dark:text-gray-400">My</span>
                        <RatingStars
                          value={spot.my_rating}
                          interactive
                          onRate={(r) => rateFoodAtSpot(spot.id, r, spot.my_review || '')}
                          size="sm"
                        />
                      </div>
                    )}
                  </div>
                )}
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-600">
                  <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Reviews</p>
                  {user && (
                    <FoodReviewForm
                      key={spot.id}
                      food={{ id: food.id, my_review: spot.my_review, my_rating: spot.my_rating }}
                      onSave={(note) => rateFoodAtSpot(spot.id, spot.my_rating ?? 3, note)}
                    />
                  )}
                  {!user && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Log in to add a review.</p>
                  )}
                  {spot.reviews && spot.reviews.length > 0 ? (
                    <ul className="mt-3 space-y-2 max-h-40 overflow-y-auto">
                      {spot.reviews.map((r) => (
                        <li key={r.id} className="text-sm p-2 rounded bg-white dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700">
                          <div className="flex items-center gap-2 mb-0.5">
                            <RatingStars value={r.rating} size="sm" />
                            <span className="text-xs text-gray-500 dark:text-gray-400">{r.added_by_username}</span>
                          </div>
                          {r.note && <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{r.note}</p>}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">No reviews yet.</p>
                  )}
                </div>
                <Link
                  to={`/spot/${spot.id}`}
                  className="inline-flex items-center gap-1 text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline mt-2"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
                  </svg>
                  Show spot detail
                </Link>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
