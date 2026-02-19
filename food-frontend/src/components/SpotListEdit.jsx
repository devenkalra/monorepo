import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function SpotListEdit({ apiBase }) {
  const { id: idParam } = useParams();
  const id = idParam && idParam !== 'create' ? idParam : null;
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [selectedSpotIds, setSelectedSpotIds] = useState([]);
  const [spots, setSpots] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!!id);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.fetch(`${apiBase}/spots/`);
        const data = await res.json();
        setSpots(Array.isArray(data) ? data : data.results || []);
      } catch (err) {
        console.error('Failed to load spots', err);
      }
    })();
  }, [apiBase]);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      try {
        const res = await api.fetch(`${apiBase}/spot-lists/${id}/`);
        const data = await res.json();
        setName(data.name || '');
        setSelectedSpotIds((data.spots || []).map((s) => s.id));
      } catch (err) {
        console.error('Failed to load list', err);
      } finally {
        setLoading(false);
      }
    })();
  }, [apiBase, id]);

  const toggleSpot = (spotId) => {
    setSelectedSpotIds((prev) =>
      prev.includes(spotId) ? prev.filter((x) => x !== spotId) : [...prev, spotId]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name, spots: selectedSpotIds };
      if (id) {
        await api.fetch(`${apiBase}/spot-lists/${id}/`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      } else {
        await api.fetch(`${apiBase}/spot-lists/`, {
          method: 'POST',
          body: JSON.stringify(body),
        });
      }
      navigate(id ? `/spot-lists/${id}` : '/spot-lists');
    } catch (err) {
      console.error('Failed to save', err);
      alert('Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-center text-gray-500 py-8">Loading…</p>;

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-center justify-between gap-4 mb-4">
          <button type="button" onClick={() => navigate(-1)} className="text-sm text-amber-600 dark:text-amber-400 hover:underline">
            ← Back
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-sm"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">List name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Spots</label>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {spots.map((s) => (
              <label key={s.id} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedSpotIds.includes(s.id)}
                  onChange={() => toggleSpot(s.id)}
                />
                <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
