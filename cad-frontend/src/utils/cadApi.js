import { getApiBaseUrl } from './apiUrl';

/** Build full URL for CAD API (geometry, textures, env) - used by Three.js loaders */
export const getCadUrl = (path) => {
  const base = getApiBaseUrl();
  const p = path.startsWith('/') ? path : `/${path}`;
  return base ? `${base}${p}` : p;
};

/** Get auth headers for fetch (needed when loader doesn't use api.fetch) */
export const getCadAuthHeaders = () => {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};
