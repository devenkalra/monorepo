export const getApiBaseUrl = () => {
  // Use relative URLs so the dev server proxies /api to the backend.
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return '';
    }
  }
  return '';
};
