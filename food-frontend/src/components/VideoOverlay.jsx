import React, { useEffect } from 'react';
import { getYouTubeEmbedUrl } from '../utils/youtube';

/** Overlay modal that plays a YouTube video. Click backdrop or close button to dismiss. */
export default function VideoOverlay({ videoId, onClose }) {
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', handleEscape);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  if (!videoId) return null;

  const embedUrl = getYouTubeEmbedUrl(videoId);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div className="relative w-full max-w-4xl aspect-video bg-black rounded-lg overflow-hidden shadow-2xl">
        <button
          onClick={onClose}
          className="absolute top-2 right-2 z-10 p-2 bg-black/60 text-white rounded-full hover:bg-black/80"
          aria-label="Close"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        <iframe
          src={embedUrl}
          title="YouTube video"
          className="w-full h-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    </div>
  );
}
