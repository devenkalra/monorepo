export const getApiBaseUrl = () => '';

export const getMediaUrl = (url) => {
  if (!url) return url;
  if (url.startsWith('http')) return url;
  if (typeof window !== 'undefined') {
    return `${window.location.origin}${url.startsWith('/') ? url : '/' + url}`;
  }
  return url;
};
