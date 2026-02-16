// Helper to get the correct API base URL
export const getApiBaseUrl = () => {
  // Use relative URLs so the dev server (or nginx) proxies /api to the backend.
  // This works for container (5175/5176), people (5173), cad (5174) - all have /api proxy.
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return ''; // Relative - proxy handles /api
    }
  }
  return '';
};

export const getMediaUrl = (url) => {
  if (!url) return url;
  if (url.startsWith('http')) return url;

  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return `${window.location.origin}${url.startsWith('/') ? url : '/' + url}`;
    }
  }
  return url;
};
