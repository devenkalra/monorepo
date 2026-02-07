import React from 'react';
import { getMediaUrl } from '../utils/apiUrl';

function EntityList({ entities, onEntityClick, selectionMode = false, selectedEntityIds = new Set(), onToggleSelection }) {
    if (!entities.length) {
        return <p className="text-center text-gray-500">No entities found.</p>;
    }

    const getFirstPhotoThumbnail = (entity) => {
        if (!entity.photos || entity.photos.length === 0) return null;
        
        const firstPhoto = entity.photos[0];
        // Handle both old format (string) and new format (object)
        const thumbnailUrl = typeof firstPhoto === 'string' 
            ? firstPhoto 
            : (firstPhoto.thumbnail_url || firstPhoto.url);
        
        return getMediaUrl(thumbnailUrl);
    };

    return (
        <ul className="space-y-2">
            {entities.map((entity) => {
                const thumbnailUrl = getFirstPhotoThumbnail(entity);
                const isSelected = selectedEntityIds.has(entity.id);
                
                return (
                    <li
                        key={entity.id}
                        onClick={() => {
                            if (selectionMode) {
                                onToggleSelection(entity.id);
                            } else {
                                onEntityClick(entity);
                            }
                        }}
                        className={`p-3 rounded bg-white dark:bg-gray-800 shadow hover:shadow-md transition cursor-pointer ${
                            isSelected ? 'ring-2 ring-blue-500' : ''
                        }`}
                    >
                        <div className="flex gap-3 items-center">
                            {/* Checkbox in selection mode */}
                            {selectionMode && (
                                <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => onToggleSelection(entity.id)}
                                    onClick={(e) => e.stopPropagation()}
                                    className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                            )}
                            {/* Thumbnail Icon or Letter Avatar */}
                            {thumbnailUrl ? (
                                <img
                                    src={thumbnailUrl}
                                    alt=""
                                    className="w-12 h-12 rounded object-cover flex-shrink-0"
                                />
                            ) : (
                                <div className="w-12 h-12 rounded bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                                    <span className="text-white text-xl font-bold">
                                        {(entity.display || entity.label || '?')[0].toUpperCase()}
                                    </span>
                                </div>
                            )}
                            
                            {/* Entity Info */}
                            <div className="flex-1 min-w-0">
                                <div className="flex justify-between items-start gap-2">
                                    <div className="flex-1 min-w-0">
                                        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 truncate">
                                            {entity.display || entity.label}
                                        </h2>
                                        <p className="text-sm text-gray-600 dark:text-gray-300">
                                            {entity.type}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap gap-1 justify-end">
                                        {entity.tags &&
                                            entity.tags.slice(0, 3).map((tag) => (
                                                <span
                                                    key={tag}
                                                    className="px-2 py-0.5 text-xs rounded bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 whitespace-nowrap"
                                                >
                                                    {tag}
                                                </span>
                                            ))}
                                        {entity.tags && entity.tags.length > 3 && (
                                            <span className="px-2 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
                                                +{entity.tags.length - 3}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </li>
                );
            })}
        </ul>
    );
}

export default EntityList;
