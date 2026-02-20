import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../services/api';
import MediaSection from './MediaSection';
import YouTubeSection from './YouTubeSection';
import TagInput from './TagInput';
import SearchableCheckboxList from './SearchableCheckboxList';

export default function FoodSpotEdit({ apiBase }) {
  const { id: idParam } = useParams();
  const id = idParam && idParam !== 'create' ? idParam : null;
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [locations, setLocations] = useState([{ street: '', city: '', state: '', country: '', postal_code: '', phone: '' }]);
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [urls, setUrls] = useState([]);
  const [selectedFoodIds, setSelectedFoodIds] = useState([]);
  const [foods, setFoods] = useState([]);
  const [foodsLoading, setFoodsLoading] = useState(true);
  const [foodsError, setFoodsError] = useState(null);
  const [isPrivate, setIsPrivate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!!id);

  useEffect(() => {
    (async () => {
      setFoodsLoading(true);
      setFoodsError(null);
      try {
        const res = await api.fetch(`${apiBase}/foods/`);
        const data = await res.json();
        if (!res.ok) {
          setFoodsError(res.status === 401 ? 'Log in to manage foods' : 'Failed to load foods');
          setFoods([]);
        } else {
          setFoods(Array.isArray(data) ? data : data.results || []);
        }
      } catch (err) {
        console.error('Failed to load foods', err);
        setFoodsError('Failed to load foods');
        setFoods([]);
      } finally {
        setFoodsLoading(false);
      }
    })();
  }, [apiBase]);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const res = await api.fetch(`${apiBase}/spots/${id}/`);
        const data = await res.json();
        setName(data.name || '');
        setLocations(Array.isArray(data.locations) && data.locations.length > 0
          ? data.locations.map((l) => ({
              street: l.street || '',
              city: l.city || '',
              state: l.state || '',
              country: l.country || '',
              postal_code: l.postal_code || '',
              phone: l.phone || '',
            }))
          : [{ street: '', city: '', state: '', country: '', postal_code: '', phone: '' }]);
        setDescription(data.description || '');
        setTags(data.tags || []);
        setPhotos(data.photos || []);
        setUrls(data.urls || []);
        setSelectedFoodIds((data.foods || []).map((f) => f.id));
        setIsPrivate(data.private ?? false);
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
      const cleaned = locations.filter((l) => l.street || l.city || l.state || l.country || l.postal_code || l.phone);
      const body = { name, locations: cleaned, description, tags, photos, urls, foods: selectedFoodIds, private: isPrivate };
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
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Foods served here</label>
          <SearchableCheckboxList
            items={foods}
            selectedIds={selectedFoodIds}
            onChange={setSelectedFoodIds}
            loading={foodsLoading}
            error={foodsError}
            emptyMessage="No foods yet. Create foods first, then add them here."
            placeholder="Search foods…"
          />
        </div>
        <div>
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Locations</label>
          <div className="space-y-4">
            {locations.map((loc, idx) => (
              <div key={idx} className="p-4 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 space-y-2">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Location {idx + 1}</span>
                  {locations.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setLocations((prev) => prev.filter((_, i) => i !== idx))}
                      className="text-sm text-red-600 dark:text-red-400 hover:underline"
                    >
                      Remove
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Street"
                    value={loc.street}
                    onChange={(e) => {
                      const next = [...locations];
                      next[idx] = { ...next[idx], street: e.target.value };
                      setLocations(next);
                    }}
                    className="sm:col-span-2 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="City"
                    value={loc.city}
                    onChange={(e) => {
                      const next = [...locations];
                      next[idx] = { ...next[idx], city: e.target.value };
                      setLocations(next);
                    }}
                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="State"
                    value={loc.state}
                    onChange={(e) => {
                      const next = [...locations];
                      next[idx] = { ...next[idx], state: e.target.value };
                      setLocations(next);
                    }}
                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="Country"
                    value={loc.country}
                    onChange={(e) => {
                      const next = [...locations];
                      next[idx] = { ...next[idx], country: e.target.value };
                      setLocations(next);
                    }}
                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="Postal Code"
                    value={loc.postal_code}
                    onChange={(e) => {
                      const next = [...locations];
                      next[idx] = { ...next[idx], postal_code: e.target.value };
                      setLocations(next);
                    }}
                    className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                  <input
                    type="tel"
                    placeholder="Phone"
                    value={loc.phone}
                    onChange={(e) => {
                      const next = [...locations];
                      next[idx] = { ...next[idx], phone: e.target.value };
                      setLocations(next);
                    }}
                    className="sm:col-span-2 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                  />
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setLocations((prev) => [...prev, { street: '', city: '', state: '', country: '', postal_code: '', phone: '' }])}
              className="text-sm text-amber-600 dark:text-amber-400 hover:underline"
            >
              + Add location
            </button>
          </div>
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
