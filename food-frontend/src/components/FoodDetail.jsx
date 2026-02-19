import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import MediaSection from './MediaSection';
import YouTubeSection from './YouTubeSection';

export default function FoodDetail({ apiBase, user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [food, setFood] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!id) return;
    (async () => {
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
    })();
  }, [apiBase, id]);

  if (loading) return <p className="text-center text-gray-500 py-8">Loading…</p>;
  if (!food) return <p className="text-center text-gray-500 py-8">Not found.</p>;

  const canEdit = user && food.added_by === (user.id ?? user.pk);

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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{food.name}</h1>
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
          <p className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Served at</p>
          <ul className="space-y-1">
            {food.served_at.map((s) => (
              <li key={s.id}>
                <Link
                  to={`/spot/${s.id}`}
                  className="text-amber-600 dark:text-amber-400 hover:underline"
                >
                  {s.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
