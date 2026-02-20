import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import MediaSection from './MediaSection';
import YouTubeSection from './YouTubeSection';
import TagInput from './TagInput';
import SearchableCheckboxList from './SearchableCheckboxList';

export default function FoodEdit({ apiBase }) {
  const { id: idParam } = useParams();
  const [searchParams] = useSearchParams();
  const id = idParam && idParam !== 'create' ? idParam : null;
  const navigate = useNavigate();
  const initialName = id ? '' : (searchParams.get('name') || '');
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState('');
  const [alsocalled, setAlsocalled] = useState('');
  const [tags, setTags] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [urls, setUrls] = useState([]);
  const [selectedSpotIds, setSelectedSpotIds] = useState([]);
  const [spots, setSpots] = useState([]);
  const [isPrivate, setIsPrivate] = useState(false);
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
        const res = await api.fetch(`${apiBase}/foods/${id}/`);
        const data = await res.json();
        setName(data.name || '');
        setDescription(data.description || '');
        setAlsocalled(data.alsocalled || '');
        setTags(data.tags || []);
        setPhotos(data.photos || []);
        setUrls(data.urls || []);
        setSelectedSpotIds((data.served_at || []).map((s) => s.id));
        setIsPrivate(data.private ?? false);
      } catch (err) {
        console.error('Failed to load food', err);
      } finally {
        setLoading(false);
      }
    })();
  }, [apiBase, id]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name, description, alsocalled, tags, photos, urls, served_at: selectedSpotIds, private: isPrivate };
      if (id) {
        await api.fetch(`${apiBase}/foods/${id}/`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      } else {
        await api.fetch(`${apiBase}/foods/`, {
          method: 'POST',
          body: JSON.stringify(body),
        });
      }
      navigate(id ? `/food/${id}` : '/foods');
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
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Served at (spots)</label>
          <SearchableCheckboxList
            items={spots}
            selectedIds={selectedSpotIds}
            onChange={setSelectedSpotIds}
            emptyMessage="No spots yet. Create spots first, then add them here."
            placeholder="Search spots…"
          />
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
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Tags</label>
          <TagInput value={tags} onChange={setTags} />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">Also called</label>
          <input
            type="text"
            value={alsocalled}
            onChange={(e) => setAlsocalled(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          />
        </div>
        <MediaSection photos={photos} onChange={setPhotos} />
        <YouTubeSection urls={urls} onChange={setUrls} />
        <div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Private (only visible to you)</span>
          </label>
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
