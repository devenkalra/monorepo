import React from 'react';

const FOOD_HELP = (
  <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
    <p><strong>Food</strong> — Track and share favorite, dishes and food spots.</p>
    <ul className="list-disc list-inside space-y-1 ml-2">
      <li><strong>Spots</strong> — Restaurants, cafes, food trucks. Add locations, photos, tags.</li>
      <li><strong>Foods</strong> — Dishes or items. Link them to spots where they&apos;re served.</li>
      <li><strong>Spot Lists</strong> — Create and share lists like &quot;Best tacos in town&quot; or &quot;Date night spots&quot;.</li>
      <li><strong>Food Lists</strong> — Create and share bucket list of dishes to try or favorites.</li>
    </ul>
  </div>
);

export default function HelpModal({ open, onClose }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6 border border-gray-200 dark:border-gray-600"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Help — Food</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-2xl leading-none"
          >
            ×
          </button>
        </div>
        {FOOD_HELP}
      </div>
    </div>
  );
}
