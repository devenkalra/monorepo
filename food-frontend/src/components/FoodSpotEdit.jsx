import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../services/api';
import MediaSection from './MediaSection';
import YouTubeSection from './YouTubeSection';
import TagInput from './TagInput';

export default function FoodSpotEdit({ apiBase }) {
  const { id: idParam } = useParams();
  const id = idParam && idParam !== 'create' ? idParam : null;
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [urls, setUrls] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!!id);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const res = await api.fetch(`${apiBase}/spots/${id}/`);
        const data = await res.json();
        setName(data.name || '');
        setLocation(data.location || '');
        setDescription(data.description || '');
        setTags(data.tags || []);
        setPhotos(data.photos || []);
        setUrls(data.urls || []);
      } catch (err) {
        console.error('Failed to load food spot', err);
      } finally {
        setLoading(false);
      }
    })();
  }, [apiBase, id]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name, location, description, tags, photos, urls };
      if (id) {
        await api.fetch(`${apiBase}/spots/${id}/`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      } else {
        await api.fetch(`${apiBase}/spots/`, {
          method: 'POST',
          body: JSON.stringify(body),
        });
      }
      navigate(id ? `/spot/${id}` : '/');
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
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Location</label>
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Tags</label>
          <TagInput value={tags} onChange={setTags} />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          />
        </div>
        <MediaSection photos={photos} onChange={setPhotos} />
        <YouTubeSection urls={urls} onChange={setUrls} />
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
