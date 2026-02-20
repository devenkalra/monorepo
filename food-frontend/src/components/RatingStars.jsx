import React from 'react';

/** Display rating as stars (1-5). Optionally interactive for submitting rating. */
export default function RatingStars({ value, count, interactive, onRate, size = 'sm' }) {
  const sizeClass = size === 'lg' ? 'w-5 h-5' : 'w-4 h-4';
  const stars = [1, 2, 3, 4, 5];

  return (
    <span className="inline-flex items-center gap-0.5">
      {stars.map((star) => (
        <button
          key={star}
          type="button"
          disabled={!interactive}
          onClick={() => interactive && onRate && onRate(star)}
          className={`${interactive ? 'cursor-pointer hover:scale-110 transition' : 'cursor-default'} p-0 border-0 bg-transparent`}
          title={interactive ? `Rate ${star} star${star > 1 ? 's' : ''}` : null}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className={`${sizeClass} ${value != null && star <= value ? 'text-amber-500' : 'text-gray-300 dark:text-gray-600'}`}
          >
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 0 0 .95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 0 0-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 0 0-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 0 0-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 0 0 .951-.69l1.07-3.292Z" />
          </svg>
        </button>
      ))}
      {count != null && count > 0 && (
        <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">({count})</span>
      )}
    </span>
  );
}
