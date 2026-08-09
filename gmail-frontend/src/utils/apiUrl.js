export const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  if (typeof window !== 'undefined') {
    const { protocol, hostname, port } = window.location;
    if (port === '80' || port === '443' || port === '') return '';
    if (port === '5177') return `${protocol}//${hostname}:8000`;
    return '';
  }
  return '';
};
