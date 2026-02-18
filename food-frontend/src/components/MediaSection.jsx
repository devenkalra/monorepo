import React, { useRef, useState, useCallback } from 'react';
import api from '../services/api';
import { getMediaUrl } from '../utils/apiUrl';

/** Reusable media (photos) section - upload, display, delete. Same scheme as people app. */
export default function MediaSection({ photos = [], onChange, readOnly = false }) {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const uploadFile = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.fetch('/api/upload/', { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');
    return res.json();
  };

  const processFiles = useCallback(async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f.type?.startsWith('image/'));
    if (!files.length) return;
    const list = [...(photos || [])];
    for (const file of files) {
      try {
        const result = await uploadFile(file);
        list.push({
          url: result.url,
          thumbnail_url: result.thumbnail_url || result.url,
          filename: file.name,
          caption: '',
        });
      } catch (err) {
        console.error('Upload failed:', err);
      }
    }
    onChange(list);
  }, [photos, onChange]);

  const handleAdd = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    await processFiles(files);
    e.target.value = '';
  };

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!readOnly) setIsDragging(true);
  }, [readOnly]);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!e.currentTarget.contains(e.relatedTarget)) setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (readOnly) return;
    const files = e.dataTransfer.files;
    if (files?.length) processFiles(files);
    // Handle image URL from webpage drag (e.g. drag image from browser)
    const items = e.dataTransfer.items;
    if (items && !files?.length) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
          const file = items[i].getAsFile();
          if (file?.type?.startsWith('image/')) processFiles([file]);
          break;
        }
        if (items[i].kind === 'string' && items[i].type === 'text/uri-list') {
          items[i].getAsString((url) => {
            fetch(url, { mode: 'cors' })
              .then((r) => r.blob())
              .then((blob) => {
                const file = new File([blob], 'image.png', { type: blob.type || 'image/png' });
                processFiles([file]);
              })
              .catch(() => {});
          });
          break;
        }
      }
    }
  }, [readOnly, processFiles]);

  const handleRemove = (idx) => {
    const list = [...(photos || [])];
    list.splice(idx, 1);
    onChange(list);
  };

  const handleCaptionChange = (idx, caption) => {
    const list = photos.map((p, i) => {
      if (i !== idx) return p;
      const obj = typeof p === 'string' ? { url: p } : { ...p };
      return { ...obj, caption };
    });
    onChange(list);
  };

  if (readOnly && (!photos || photos.length === 0)) return null;

  return (
    <div
      className={`space-y-2 ${!readOnly ? 'min-h-[60px]' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="flex items-center justify-between">
        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400">Photos</label>
        {!readOnly && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={handleAdd}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="text-sm text-amber-600 dark:text-amber-400 hover:underline"
            >
              + Add photos
            </button>
          </>
        )}
      </div>
      {!readOnly && (
        <div
          className={`rounded-lg border-2 border-dashed p-4 text-center text-sm text-gray-500 dark:text-gray-400 transition-colors ${
            isDragging
              ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20'
              : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
          }`}
        >
          Drop images here (files or from a webpage)
        </div>
      )}
      {photos && photos.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
          {photos.map((photo, idx) => {
            const url = typeof photo === 'string' ? photo : photo.url;
            const thumb = typeof photo === 'string' ? photo : (photo.thumbnail_url || photo.url);
            const caption = typeof photo === 'string' ? '' : (photo.caption || '');
            return (
              <div key={idx} className="relative group">
                <img
                  src={getMediaUrl(thumb)}
                  alt={caption || ''}
                  className="w-full aspect-square object-cover rounded border border-gray-200 dark:border-gray-600"
                />
                {!readOnly && (
                  <button
                    type="button"
                    onClick={() => handleRemove(idx)}
                    className="absolute top-1 right-1 p-1 bg-red-600 text-white rounded-full hover:bg-red-700 text-xs"
                    aria-label="Remove"
                  >
                    ×
                  </button>
                )}
                {!readOnly ? (
                  <input
                    type="text"
                    value={caption}
                    onChange={(e) => handleCaptionChange(idx, e.target.value)}
                    placeholder="Add caption"
                    className="mt-1 w-full px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                ) : caption ? (
                  <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 truncate" title={caption}>{caption}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
