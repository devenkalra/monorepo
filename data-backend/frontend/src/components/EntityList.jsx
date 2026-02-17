import React, { useState, useRef, useCallback } from 'react';
import { getMediaUrl } from '../utils/apiUrl';

/** Shorten each part of a hierarchical tag to first 3 chars (e.g. people/family → peo/fam) */
function shortenTag(tag) {
    if (!tag || typeof tag !== 'string') return tag;
    return tag.split('/').map(part => part.slice(0, 3)).join('/');
}

/** Single-letter badge for entity type */
const TYPE_LETTER = {
    Person: 'P', Note: 'N', Location: 'L', Org: 'O', Movie: 'M', Book: 'B', Container: 'C', Asset: 'A',
};

function getTypeLetter(type) {
    return (type && TYPE_LETTER[type]) || (type ? type[0] : '?');
}

/** Renders a single entity row with type overlay and hover/long-press details */
function EntityListItem({ entity, thumbnailUrl, isSelected, selectionMode, onToggleSelection, onEntityClick }) {
    const [showOverlay, setShowOverlay] = useState(false);
    const longPressTimer = useRef(null);
    const longPressTriggered = useRef(false);

    const handleLongPressStart = useCallback(() => {
        longPressTriggered.current = false;
        longPressTimer.current = setTimeout(() => {
            longPressTimer.current = null;
            longPressTriggered.current = true;
            setShowOverlay(true);
        }, 600);
    }, []);

    const handleLongPressEnd = useCallback(() => {
        if (longPressTimer.current) {
            clearTimeout(longPressTimer.current);
            longPressTimer.current = null;
        }
    }, []);

    const handleClick = useCallback((e) => {
        if (selectionMode) {
            onToggleSelection(entity.id);
            return;
        }
        if (showOverlay) {
            e.stopPropagation();
            setShowOverlay(false);
            return;
        }
        if (longPressTriggered.current) {
            e.stopPropagation();
            longPressTriggered.current = false;
            return;
        }
        onEntityClick(entity);
    }, [selectionMode, showOverlay, entity, onEntityClick, onToggleSelection]);

    // Only use hover on devices that support it (desktop); touch devices use long-press only
    const handleMouseEnter = useCallback(() => {
        if (typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches) {
            setShowOverlay(true);
        }
    }, []);
    const handleMouseLeave = useCallback(() => {
        if (typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches) {
            setShowOverlay(false);
        }
    }, []);

    const typeLetter = getTypeLetter(entity.type);

    return (
        <li
            onClick={handleClick}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            onTouchStart={handleLongPressStart}
            onTouchEnd={handleLongPressEnd}
            onTouchMove={handleLongPressEnd}
            onTouchCancel={handleLongPressEnd}
            className={`p-3 rounded bg-white dark:bg-gray-800 shadow hover:shadow-md transition cursor-pointer relative ${
                isSelected ? 'ring-2 ring-blue-500' : ''
            }`}
        >
            <div className="flex gap-3 items-center">
                {selectionMode && (
                    <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => onToggleSelection(entity.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                )}
                {/* Thumbnail with type badge overlay */}
                <div className="relative flex-shrink-0">
                    {thumbnailUrl ? (
                        <img src={thumbnailUrl} alt="" className="w-12 h-12 rounded object-cover" />
                    ) : (
                        <div className="w-12 h-12 rounded bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                            <span className="text-white text-xl font-bold">
                                {(entity.display || entity.label || '?')[0].toUpperCase()}
                            </span>
                        </div>
                    )}
                    <span
                        className="absolute top-0 left-0 w-4 h-4 flex items-center justify-center rounded-bl rounded-tr bg-gray-900/80 text-white dark:bg-white/80 dark:text-gray-900 text-[9px] font-bold"
                        title={entity.type}
                    >
                        {typeLetter}
                    </span>
                </div>
                {/* Entity Info */}
                <div className="flex-1 min-w-0 flex flex-col gap-1">
                    <div className="min-w-0">
                        <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100 truncate">
                            {entity.display || entity.label}
                        </h2>
                    </div>
                    {entity.tags && entity.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-0.5">
                            {entity.tags.slice(0, 5).map((tag) => (
                                <span
                                    key={tag}
                                    className="px-1.5 py-0.5 text-[10px] sm:text-xs rounded bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200"
                                    title={tag}
                                >
                                    {shortenTag(tag)}
                                </span>
                            ))}
                            {entity.tags.length > 5 && (
                                <span className="px-1.5 py-0.5 text-[10px] sm:text-xs rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
                                    +{entity.tags.length - 5}
                                </span>
                            )}
                        </div>
                    )}
                </div>
            </div>
            {/* Hover / long-press overlay */}
            {showOverlay && (
                <div
                    className="absolute inset-0 z-10 rounded bg-gray-900/80 dark:bg-gray-950/80 text-white p-3 overflow-auto"
                    onClick={(e) => { e.stopPropagation(); setShowOverlay(false); }}
                >
                    <div className="text-xs space-y-2" onClick={(e) => e.stopPropagation()}>
                        <div className="flex justify-between items-start">
                            <span className="font-semibold text-sm">{entity.display || entity.label || 'Untitled'}</span>
                            <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); setShowOverlay(false); }}
                                className="text-gray-400 hover:text-white p-0.5 -m-0.5"
                                aria-label="Close"
                            >
                                ✕
                            </button>
                        </div>
                        <dl className="space-y-1">
                            <div><dt className="text-gray-400">Type</dt><dd>{entity.type}</dd></div>
                            {entity.tags?.length > 0 && (
                                <div><dt className="text-gray-400">Tags</dt><dd>{entity.tags.join(', ')}</dd></div>
                            )}
                        </dl>
                    </div>
                </div>
            )}
        </li>
    );
}

function EntityList({ entities, onEntityClick, selectionMode = false, selectedEntityIds = new Set(), onToggleSelection }) {
    if (!entities.length) {
        return <p className="text-center text-gray-500">No entities found.</p>;
    }

    const getFirstPhotoThumbnail = (entity) => {
        if (!entity.photos || entity.photos.length === 0) return null;
        const firstPhoto = entity.photos[0];
        const thumbnailUrl = typeof firstPhoto === 'string'
            ? firstPhoto
            : (firstPhoto.thumbnail_url || firstPhoto.url);
        return getMediaUrl(thumbnailUrl);
    };

    return (
        <ul className="space-y-2">
            {entities.map((entity) => (
                <EntityListItem
                    key={entity.id}
                    entity={entity}
                    thumbnailUrl={getFirstPhotoThumbnail(entity)}
                    isSelected={selectedEntityIds.has(entity.id)}
                    selectionMode={selectionMode}
                    onToggleSelection={onToggleSelection}
                    onEntityClick={onEntityClick}
                />
            ))}
        </ul>
    );
}

export default EntityList;
