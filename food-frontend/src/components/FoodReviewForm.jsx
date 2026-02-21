import React, { useState, useEffect } from 'react';

/** Form to add/edit a review (note) for a food at a spot. */
export default function FoodReviewForm({ food, onSave }) {
  const [note, setNote] = useState(food.my_review || '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setNote(food.my_review || '');
  }, [food.id, food.my_review]);

  const handleSave = async () => {
    if (!onSave) return;
    setSaving(true);
    try {
      await onSave(note);
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = note !== (food.my_review || '');

  return (
    <div className="mt-2">
      <label className="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">My review</label>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Add a review for this food at this spot…"
        rows={3}
        className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400"
      />
      {hasChanges && (
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="mt-1 text-sm font-medium text-amber-600 dark:text-amber-400 hover:underline disabled:opacity-50 disabled:no-underline"
        >
          {saving ? 'Saving…' : 'Save review'}
        </button>
      )}
    </div>
  );
}
