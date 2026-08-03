const SESSION_KEY = 'dk_sid';
const DEDUPE_PREFIX = 'dk_pv:';

function getSessionKey() {
  try {
    let key = sessionStorage.getItem(SESSION_KEY);
    if (!key) {
      key =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `s_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem(SESSION_KEY, key);
    }
    return key;
  } catch {
    return '';
  }
}

function shouldSkipPath(pathname) {
  if (!pathname) return true;
  if (pathname.startsWith('/login/google/callback')) return true;
  if (pathname.startsWith('/login/github/callback')) return true;
  return false;
}

/**
 * Fire a best-effort page_view for the current SPA location.
 * Uses pathname only (ignores query) so Notes UI params do not spam events.
 * Dedupes per browser tab session + pathname.
 */
export function trackPageView({ path, token } = {}) {
  if (typeof window === 'undefined') return;
  const pathname = (path || window.location.pathname || '').split('?')[0];
  if (shouldSkipPath(pathname)) return;

  const dedupeKey = `${DEDUPE_PREFIX}${pathname}`;
  try {
    if (sessionStorage.getItem(dedupeKey)) return;
    sessionStorage.setItem(dedupeKey, '1');
  } catch {
    /* still send once if storage blocked */
  }

  const payload = JSON.stringify({
    event: 'page_view',
    path: pathname.slice(0, 500),
    referrer: document.referrer || '',
    session_key: getSessionKey(),
  });

  const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (token) headers.Authorization = `Token ${token}`;

  const url = '/api/analytics/events/';

  try {
    if (navigator.sendBeacon && !token) {
      // sendBeacon cannot set Authorization; use fetch when logged in
      const blob = new Blob([payload], { type: 'application/json' });
      if (navigator.sendBeacon(url, blob)) return;
    }
  } catch {
    /* fall through */
  }

  try {
    fetch(url, {
      method: 'POST',
      headers,
      body: payload,
      keepalive: true,
      credentials: 'omit',
    }).catch(() => {});
  } catch {
    /* ignore analytics failures */
  }
}
