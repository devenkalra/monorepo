import React from 'react';

const PEOPLE_HELP = (
  <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
    <p><strong>Entity Browser (Second Brain)</strong> — Capture people, places, notes, and ideas in a connected knowledge graph.</p>
    <ul className="list-disc list-inside space-y-1 ml-2">
      <li><strong>Search</strong> — Find entities by name, tags, or content.</li>
      <li><strong>Tags</strong> — Organize with hierarchical tags (e.g. people/family).</li>
      <li><strong>Relations</strong> — Link entities (person → knows → person).</li>
      <li><strong>Import</strong> — Bring in conversations from ChatGPT or similar exports.</li>
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
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Help — People</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-2xl leading-none"
          >
            ×
          </button>
        </div>
        {PEOPLE_HELP}
      </div>
    </div>
  );
}
