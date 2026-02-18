import React, { useState } from 'react';
import { getYouTubeVideoId, getYouTubeThumbnailUrl } from '../utils/youtube';
import VideoOverlay from './VideoOverlay';

/** Edit mode: add/remove YouTube URLs. Detail mode: show thumbnails, click to play in overlay. */
export default function YouTubeSection({ urls = [], onChange, readOnly = false }) {
  const [inputValue, setInputValue] = useState('');
  const [playingVideoId, setPlayingVideoId] = useState(null);

  const youtubeUrls = (urls || []).filter((u) => {
    const url = typeof u === 'string' ? u : u?.url;
    return url && getYouTubeVideoId(url);
  });

  const addUrl = () => {
    const trimmed = inputValue.trim();
    const videoId = getYouTubeVideoId(trimmed);
    if (!videoId) {
      alert('Please enter a valid YouTube URL (e.g. https://www.youtube.com/watch?v=VIDEO_ID or https://youtu.be/VIDEO_ID)');
      return;
    }
    const normalized = `https://www.youtube.com/watch?v=${videoId}`;
    if (youtubeUrls.some((u) => (typeof u === 'string' ? u : u.url) === normalized)) {
      return;
    }
    onChange([...(urls || []), { url: normalized }]);
    setInputValue('');
  };

  const removeUrl = (idx) => {
    const item = youtubeUrls[idx];
    const url = typeof item === 'string' ? item : item?.url;
    onChange(urls.filter((u) => (typeof u === 'string' ? u : u?.url) !== url));
  };

  const openVideo = (url) => {
    const videoId = getYouTubeVideoId(typeof url === 'string' ? url : url?.url);
    if (videoId) setPlayingVideoId(videoId);
  };

  if (readOnly && youtubeUrls.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400">YouTube videos</label>
      </div>

      {!readOnly && (
        <div className="flex gap-2">
          <input
            type="url"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addUrl())}
            placeholder="https://youtube.com/watch?v=..."
            className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
          />
          <button
            type="button"
            onClick={addUrl}
            className="px-3 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 text-sm"
          >
            Add
          </button>
        </div>
      )}

      {youtubeUrls.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {youtubeUrls.map((item, idx) => {
            const url = typeof item === 'string' ? item : item?.url;
            const videoId = getYouTubeVideoId(url);
            const thumb = getYouTubeThumbnailUrl(videoId);
            return (
              <div key={idx} className="relative group">
                <button
                  type="button"
                  onClick={() => readOnly && openVideo(url)}
                  className={`w-full text-left ${readOnly ? 'cursor-pointer' : ''}`}
                >
                  <img
                    src={thumb}
                    alt=""
                    className={`w-full aspect-video object-cover rounded border border-gray-200 dark:border-gray-600 ${readOnly ? 'hover:ring-2 hover:ring-amber-500' : ''}`}
                  />
                  {readOnly && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      <svg className="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M8 5v14l11-7z" />
                      </svg>
                    </div>
                  )}
                </button>
                {!readOnly && (
                  <button
                    type="button"
                    onClick={() => removeUrl(idx)}
                    className="absolute top-1 right-1 p-1 bg-red-600 text-white rounded-full hover:bg-red-700 text-xs"
                    aria-label="Remove"
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {playingVideoId && (
        <VideoOverlay videoId={playingVideoId} onClose={() => setPlayingVideoId(null)} />
      )}
    </div>
  );
}
