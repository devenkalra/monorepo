import React, { useState, useMemo } from 'react';

const DISPLAY_LIMIT = 10;

/**
 * A searchable checkbox list for selecting items. Shows first 10 items (or 10 matching search).
 * Handles thousands of items by filtering client-side and limiting display.
 *
 * @param {Object} props
 * @param {Array<{id: string, name: string}>} props.items - All items
 * @param {Array<string>} props.selectedIds - Currently selected item IDs
 * @param {function(ids: Array<string>): void} props.onChange - Called when selection changes
 * @param {boolean} props.loading - Show loading state
 * @param {string|null} props.error - Error message to show
 * @param {string} props.emptyMessage - Message when no items
 * @param {string} props.placeholder - Search input placeholder
 */
export default function SearchableCheckboxList({
  items,
  selectedIds,
  onChange,
  loading = false,
  error = null,
  emptyMessage = 'No items yet.',
  placeholder = 'Search…',
}) {
  const [search, setSearch] = useState('');

  const { filteredItems, displayedItems, totalMatchCount } = useMemo(() => {
    const q = (search || '').trim().toLowerCase();
    const filtered = q
      ? items.filter((item) => (item.name || '').toLowerCase().includes(q))
      : items;

    const selectedSet = new Set(selectedIds);
    const selectedInFiltered = filtered.filter((item) => selectedSet.has(item.id));
    const others = filtered.filter((item) => !selectedSet.has(item.id));
    const combined = [...selectedInFiltered, ...others];
    const displayed = combined.slice(0, DISPLAY_LIMIT);

    return {
      filteredItems: filtered,
      displayedItems: displayed,
      totalMatchCount: combined.length,
    };
  }, [items, search, selectedIds]);

  const toggle = (itemId) => {
    onChange(
      selectedIds.includes(itemId)
        ? selectedIds.filter((x) => x !== itemId)
        : [...selectedIds, itemId]
    );
  };

  if (loading) {
    return (
      <div className="space-y-2 p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-2 p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
        <p className="text-sm text-amber-600 dark:text-amber-400">{error}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="space-y-2 p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
        <p className="text-sm text-gray-500 dark:text-gray-400">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
      />
      <div className="max-h-48 overflow-y-auto p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 space-y-2">
        {displayedItems.map((item) => (
          <label key={item.id} className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={selectedIds.includes(item.id)}
              onChange={() => toggle(item.id)}
            />
            <span className="text-gray-700 dark:text-gray-300">{item.name}</span>
          </label>
        ))}
        {totalMatchCount > DISPLAY_LIMIT && (
          <p className="text-xs text-gray-500 dark:text-gray-400 pt-1">
            Showing {DISPLAY_LIMIT} of {totalMatchCount} matches. Refine search to find more.
          </p>
        )}
      </div>
    </div>
  );
}
