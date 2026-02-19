import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function FoodListEdit({ apiBase }) {
  const { id: idParam } = useParams();
  const id = idParam && idParam !== 'create' ? idParam : null;
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [selectedFoodIds, setSelectedFoodIds] = useState([]);
  const [foods, setFoods] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!!id);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.fetch(`${apiBase}/foods/`);
        const data = await res.json();
        setFoods(Array.isArray(data) ? data : data.results || []);
      } catch (err) {
        console.error('Failed to load foods', err);
      }
    })();
  }, [apiBase]);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      try {
        const res = await api.fetch(`${apiBase}/food-lists/${id}/`);
        const data = await res.json();
        setName(data.name || '');
        setSelectedFoodIds((data.foods || []).map((f) => f.id));
      } catch (err) {
        console.error('Failed to load list', err);
      } finally {
        setLoading(false);
      }
    })();
  }, [apiBase, id]);

  const toggleFood = (foodId) => {
    setSelectedFoodIds((prev) =>
      prev.includes(foodId) ? prev.filter((x) => x !== foodId) : [...prev, foodId]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { name, foods: selectedFoodIds };
      if (id) {
        await api.fetch(`${apiBase}/food-lists/${id}/`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      } else {
        await api.fetch(`${apiBase}/food-lists/`, {
          method: 'POST',
          body: JSON.stringify(body),
        });
      }
      navigate(id ? `/food-lists/${id}` : '/food-lists');
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
          <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-2">Foods</label>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {foods.map((f) => (
              <label key={f.id} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedFoodIds.includes(f.id)}
                  onChange={() => toggleFood(f.id)}
                />
                <span className="text-gray-700 dark:text-gray-300">{f.name}</span>
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
