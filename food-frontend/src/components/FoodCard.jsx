import React from 'react';
import { Link } from 'react-router-dom';
import RatingStars from './RatingStars';

/**
 * Reusable card for displaying a food. Used in FoodsList, FoodListDetail, FoodSpotDetail, etc.
 * Handles optional data: photos, ratings, served_at.
 * @param {object} food - Food data
 * @param {string} to - Override link href (default: /food/:id)
 * @param {'link'|'button'} as - Render as Link or button (for expandable in detail pages)
 * @param {function} onClick - When as='button'
 * @param {boolean} isExpanded - When as='button', show expand state
 */
export default function FoodCard({ food, to, as = 'link', onClick, isExpanded }) {
  const href = to ?? `/food/${food.id}`;
  const photoUrl = food.photos?.[0]?.thumbnail_url || food.photos?.[0]?.url || food.photos?.[0];

  const content = (
    <>
      {photoUrl && (
        <div className="flex-shrink-0 w-10 h-10 rounded overflow-hidden bg-gray-100 dark:bg-gray-700">
          <img src={photoUrl} alt="" className="w-full h-full object-cover" />
        </div>
      )}
      <div className="flex justify-between items-center gap-2 min-w-0 flex-1">
        <div className="min-w-0 flex-1">
          <span className="font-medium text-gray-900 dark:text-gray-100">{food.name}</span>
          {food.rating_avg != null && (
            <span className="ml-2 inline-flex items-center">
              <RatingStars value={food.rating_avg} count={food.rating_count} size="sm" />
            </span>
          )}
          {food.added_by_username && (
            <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">added by {food.added_by_username}</span>
          )}
          {food.served_at_names && food.served_at_names.length > 0 && (
            <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">
              {food.served_at_names.join(', ')}
            </span>
          )}
        </div>
        <span className="text-gray-400 flex-shrink-0">
          {as === 'button' ? (isExpanded ? '▲' : '▼') : '→'}
        </span>
      </div>
    </>
  );

  const baseClass = 'flex gap-3 p-3 rounded-lg bg-white dark:bg-gray-800 shadow hover:shadow-md transition w-full text-left';

  if (as === 'button') {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${baseClass} ${isExpanded ? 'ring-1 ring-amber-300 dark:ring-amber-700 bg-amber-50/50 dark:bg-amber-900/20' : ''}`}
      >
        {content}
      </button>
    );
  }

  return (
    <Link to={href} className={baseClass}>
      {content}
    </Link>
  );
}
