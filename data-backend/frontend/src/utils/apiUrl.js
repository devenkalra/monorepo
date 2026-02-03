// Helper to get the correct API base URL
export const getApiBaseUrl = () => {
  // If we're on localhost or have port 5173 (dev server), use localhost:8000
  // Otherwise, use relative URLs (production)
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    const port = window.location.port;

    if (hostname === 'localhost' || hostname === '127.0.0.1' || port === '5173') {
      return 'http://localhost:8000';
    }
  }

  // Production: use relative URLs (nginx will proxy)
  return '';
};

export const getMediaUrl = (url) => {
  if (!url) return url;
  if (url.startsWith('http')) return url;

  // Same logic as getApiBaseUrl
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    const port = window.location.port;

    if (hostname === 'localhost' || hostname === '127.0.0.1' || port === '5173') {
      return `http://localhost:8000${url}`;
    }
  }

  return url;
};
