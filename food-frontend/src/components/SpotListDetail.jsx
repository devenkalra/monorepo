import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function SpotListDetail({ apiBase }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      try {
        const res = await api.fetch(`${apiBase}/spot-lists/${id}/`);
        const data = await res.json();
        setList(data);
      } catch (err) {
        console.error('Failed to load list', err);
        setList(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [apiBase, id]);

  if (loading) return <p className="text-center text-gray-500 py-8">Loading…</p>;
  if (!list) return <p className="text-center text-gray-500 py-8">Not found.</p>;

  return (
    <div>
      <div className="mb-4 flex justify-between items-center">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-amber-600 dark:text-amber-400 hover:underline"
        >
          ← Back
        </button>
        <Link
          to={`/spot-lists/${id}/edit`}
          className="text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline"
        >
          Edit
        </Link>
      </div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">{list.name}</h1>
      {list.spots && list.spots.length > 0 ? (
        <ul className="space-y-2">
          {list.spots.map((spot) => (
            <li key={spot.id}>
              <Link
                to={`/spot/${spot.id}`}
                className="block p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md"
              >
                {spot.name}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-gray-500">No spots in this list.</p>
      )}
    </div>
  );
}
