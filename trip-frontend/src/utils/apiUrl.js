export const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  return '';
};

export const getLoginUrl = (nextPath = '/app/trips/') => {
  const next = encodeURIComponent(
    nextPath.startsWith('/') ? nextPath : `/${nextPath}`
  );
  if (typeof window === 'undefined') {
    return `/login/?next=${next}`;
  }
  return `${window.location.origin}/login/?next=${next}`;
};
