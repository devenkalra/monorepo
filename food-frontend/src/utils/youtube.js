/** Extract YouTube video ID from various URL formats. Returns null if not a valid YouTube URL. */
export function getYouTubeVideoId(url) {
  if (!url || typeof url !== 'string') return null;
  const regExp = /^.*(youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*/;
  const match = url.trim().match(regExp);
  return match && match[2].length === 11 ? match[2] : null;
}

/** Check if URL is a YouTube URL. */
export function isYouTubeUrl(url) {
  return !!getYouTubeVideoId(url);
}

/** Get YouTube thumbnail URL for a video ID. */
export function getYouTubeThumbnailUrl(videoId, quality = 'hqdefault') {
  if (!videoId) return null;
  return `https://img.youtube.com/vi/${videoId}/${quality}.jpg`;
}

/** Get YouTube embed URL. */
export function getYouTubeEmbedUrl(videoId) {
  if (!videoId) return null;
  return `https://www.youtube.com/embed/${videoId}?autoplay=1`;
}
