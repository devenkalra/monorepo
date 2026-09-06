export const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  return '';
};

export const getLoginUrl = (nextPath = '/app/vacation/') => {
  const next = encodeURIComponent(
    nextPath.startsWith('/') ? nextPath : `/${nextPath}`
  );
  if (typeof window === 'undefined') {
    return `/login/?next=${next}`;
  }
  return `${window.location.origin}/login/?next=${next}`;
};

export const getSignupUrl = (nextPath = '/app/vacation/') => {
  // login.html hosts registration; reuse with next=
  return getLoginUrl(nextPath);
};

export const getMediaUrl = (url) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) {
    try {
      const parsed = new URL(url);
      return `${getApiBaseUrl()}${parsed.pathname}${parsed.search}`;
    } catch {
      return url;
    }
  }
  return `${getApiBaseUrl()}${url.startsWith('/') ? url : `/${url}`}`;
};
