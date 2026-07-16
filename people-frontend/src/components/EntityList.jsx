import React, { useState, useRef, useCallback, useEffect } from 'react';
import { getMediaUrl } from '../utils/apiUrl';
import { useEncryption } from '../contexts/EncryptionContext';

function DecryptedImage({ src, alt, className, onClick, title, decryptionKey }) {
    const { decryptBlob } = useEncryption();
    const [decryptedSrc, setDecryptedSrc] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!src) return;
        
        let active = true;
        const loadAndDecrypt = async () => {
            try {
                setLoading(true);
                const response = await fetch(src);
                if (!response.ok) throw new Error('Failed to fetch media');
                const encryptedBlob = await response.blob();
                
                let mimeType = 'image/jpeg';
                if (src.toLowerCase().includes('.png')) mimeType = 'image/png';
                if (src.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                if (src.toLowerCase().includes('.webp')) mimeType = 'image/webp';
                
                const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, decryptionKey);
                
                if (active) {
                    const objectUrl = URL.createObjectURL(decryptedBlob);
                    setDecryptedSrc(objectUrl);
                }
            } catch (err) {
                console.error('Failed to decrypt image in list:', err);
            } finally {
                if (active) setLoading(false);
            }
        };

        loadAndDecrypt();

        return () => {
            active = false;
            if (decryptedSrc) {
                URL.revokeObjectURL(decryptedSrc);
            }
        };
    }, [src, decryptionKey]);

    if (loading) {
        return (
            <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 animate-pulse ${className}`}>
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        );
    }

    return (
        <img
            src={decryptedSrc || src}
            alt={alt}
            className={className}
            onClick={onClick}
            title={title}
        />
    );
}

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
    const [overlayPosition, setOverlayPosition] = useState({ top: 0, left: 0 });
    const thumbnailRef = useRef(null);
    const longPressTimer = useRef(null);
    const longPressTriggered = useRef(false);
    const hideOverlayTimer = useRef(null);

    const updateOverlayPosition = useCallback(() => {
        if (thumbnailRef.current) {
            const rect = thumbnailRef.current.getBoundingClientRect();
            const overlayWidth = 220;
            const overlayMinHeight = 80;
            const gap = 8;
            const left = rect.right + gap;
            const fitsRight = left + overlayWidth <= window.innerWidth - 8;
            let top = rect.top;
            top = Math.max(8, Math.min(top, window.innerHeight - overlayMinHeight - 8));
            setOverlayPosition({
                top,
                left: fitsRight ? left : rect.left - overlayWidth - gap,
            });
        }
    }, []);

    const handleLongPressStart = useCallback(() => {
        longPressTriggered.current = false;
        longPressTimer.current = setTimeout(() => {
            longPressTimer.current = null;
            longPressTriggered.current = true;
            updateOverlayPosition();
            setShowOverlay(true);
        }, 600);
    }, [updateOverlayPosition]);

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
    // Delay hide so moving from thumbnail to overlay doesn't flicker
    const handleMouseEnter = useCallback(() => {
        if (hideOverlayTimer.current) {
            clearTimeout(hideOverlayTimer.current);
            hideOverlayTimer.current = null;
        }
        if (typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches) {
            updateOverlayPosition();
            setShowOverlay(true);
        }
    }, [updateOverlayPosition]);
    const handleMouseLeave = useCallback(() => {
        if (typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches) {
            hideOverlayTimer.current = setTimeout(() => {
                hideOverlayTimer.current = null;
                setShowOverlay(false);
            }, 150);
        }
    }, []);

    useEffect(() => () => {
        if (hideOverlayTimer.current) clearTimeout(hideOverlayTimer.current);
    }, []);

    const typeLetter = getTypeLetter(entity.type);
    const isUnlockedEncrypted = entity.is_encrypted && entity._decrypted;

    return (
        <li
            onClick={handleClick}
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
                {/* Thumbnail with type badge overlay - hover here shows overlay; click elsewhere goes to detail */}
                <div
                    ref={thumbnailRef}
                    className="relative flex-shrink-0"
                    onMouseEnter={handleMouseEnter}
                    onMouseLeave={handleMouseLeave}
                >
                    {entity.is_encrypted ? (
                        entity._decrypted ? (
                            thumbnailUrl ? (
                                <DecryptedImage
                                    src={thumbnailUrl}
                                    alt=""
                                    className="w-12 h-12 rounded object-cover"
                                    decryptionKey={entity._decryption_key}
                                />
                            ) : (
                                <div className="w-12 h-12 rounded bg-gradient-to-br from-teal-500 to-emerald-600 flex items-center justify-center">
                                    <span className="text-white text-xl font-bold">
                                        {(entity.display || entity.label || '?')[0].toUpperCase()}
                                    </span>
                                </div>
                            )
                        ) : (
                            <div className="w-12 h-12 rounded bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                                <span className="text-gray-500 dark:text-gray-400 text-xl">🔒</span>
                            </div>
                        )
                    ) : (
                        thumbnailUrl ? (
                            <img src={thumbnailUrl} alt="" className="w-12 h-12 rounded object-cover" />
                        ) : (
                            <div className="w-12 h-12 rounded bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                                <span className="text-white text-xl font-bold">
                                    {(entity.display || entity.label || '?')[0].toUpperCase()}
                                </span>
                            </div>
                        )
                    )}
                    <span
                        className="absolute top-0 left-0 w-4 h-4 flex items-center justify-center rounded-bl rounded-tr bg-gray-900/80 text-white dark:bg-white/80 dark:text-gray-900 text-[9px] font-bold"
                        title={entity.type}
                    >
                        {typeLetter}
                    </span>
                    {isUnlockedEncrypted && (
                        <span
                            className="absolute -bottom-1 -right-1 w-4 h-4 flex items-center justify-center rounded-full bg-emerald-600 text-white text-[10px] shadow"
                            title="Encrypted entity is unlocked"
                            aria-label="Encrypted entity is unlocked"
                        >
                            🔓
                        </span>
                    )}
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
            {/* Hover / long-press overlay - fixed position to the right of icon */}
            {showOverlay && (
                <div
                    className="fixed z-[9999] w-[220px] rounded-lg shadow-xl bg-white dark:bg-gray-950 text-gray-900 dark:text-white p-3 border border-gray-200 dark:border-gray-700"
                    style={{ top: overlayPosition.top, left: overlayPosition.left }}
                    onMouseEnter={handleMouseEnter}
                    onMouseLeave={handleMouseLeave}
                    onClick={(e) => { e.stopPropagation(); setShowOverlay(false); }}
                >
                    <div className="text-xs space-y-2" onClick={(e) => e.stopPropagation()}>
                        <div className="flex justify-between items-start gap-2">
                            <span className="font-semibold text-sm truncate">{entity.display || entity.label || 'Untitled'}</span>
                            <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); setShowOverlay(false); }}
                                className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white p-0.5 -m-0.5 flex-shrink-0"
                                aria-label="Close"
                            >
                                ✕
                            </button>
                        </div>
                        <dl className="space-y-1">
                            <div><dt className="text-gray-500 dark:text-gray-400">Type</dt><dd>{entity.type}</dd></div>
                            {entity.tags?.length > 0 && (
                                <div><dt className="text-gray-500 dark:text-gray-400">Tags</dt><dd className="break-words">{entity.tags.join(', ')}</dd></div>
                            )}
                        </dl>
                    </div>
                </div>
            )}
        </li>
    );
}

function EntityList({ entities, loading = false, onEntityClick, selectionMode = false, selectedEntityIds = new Set(), onToggleSelection }) {
    if (loading) {
        return <p className="text-center text-gray-500 py-8">Loading…</p>;
    }
    if (!entities.length) {
        return <p className="text-center text-gray-500 py-8">No entities found.</p>;
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
