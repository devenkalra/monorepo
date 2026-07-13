import React from 'react';
import { Link } from 'react-router-dom';
import RatingStars from './RatingStars';

/**
 * Reusable card for displaying a food spot. Used in FoodSpotsList, SpotListDetail, FoodDetail, etc.
 * Handles optional data: photos, ratings, foods pills.
 * @param {object} spot - Spot data
 * @param {string} to - Override link href (default: /spot/:id)
 * @param {'link'|'button'} as - Render as Link or button (for expandable in detail pages)
 * @param {function} onClick - When as='button'
 * @param {boolean} isExpanded - When as='button', show expand state
 */
export default function SpotCard({ spot, to, as = 'link', onClick, isExpanded }) {
  const href = to ?? `/spot/${spot.id}`;
  const photoUrl = spot.photos?.[0]?.thumbnail_url || spot.photos?.[0]?.url || spot.photos?.[0];
  const rating = spot.food_rating_avg ?? spot.rating_avg;
  const ratingCount = spot.food_rating_avg != null ? spot.food_rating_count : spot.rating_count;

  const content = (
    <>
      {photoUrl && (
        <div className="flex-shrink-0 w-10 h-10 rounded overflow-hidden bg-gray-100 dark:bg-gray-700">
          <img src={photoUrl} alt="" className="w-full h-full object-cover" />
        </div>
      )}
      <div className="flex justify-between items-center gap-2 min-w-0 flex-1">
        <div className="min-w-0 flex-1">
          <span className="font-medium text-gray-900 dark:text-gray-100">{spot.name}</span>
          {(rating != null) && (
            <span className="ml-2 inline-flex items-center">
              <RatingStars value={rating} count={ratingCount} size="sm" />
            </span>
          )}
          {spot.added_by_username && (
            <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">added by {spot.added_by_username}</span>
          )}
          {spot.foods && spot.foods.length > 0 && (
            <span className="text-sm text-gray-600 dark:text-gray-400 ml-2 flex flex-wrap gap-1">
              {spot.foods.map((f) => (
                <span
                  key={f.id}
                  className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                >
                  {f.name}
                  {f.rating_avg != null && (
                    <span className="text-amber-500 dark:text-amber-400 font-medium">★{f.rating_avg}</span>
                  )}
                </span>
              ))}
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
