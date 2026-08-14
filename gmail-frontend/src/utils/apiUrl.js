export const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  // Same-origin in prod (nginx) and on Vite :5177 (proxied to Django).
  return '';
};

/**
 * Login URL for this app.
 * On Vite :5177, /login is proxied to Django so localStorage stays on :5177.
 */
export const getLoginUrl = (nextPath = '/app/gmail/') => {
  const next = encodeURIComponent(
    nextPath.startsWith('/') ? nextPath : `/${nextPath}`
  );
  if (typeof window === 'undefined') {
    return `/login/?next=${next}`;
  }
  return `${window.location.origin}/login/?next=${next}`;
};
