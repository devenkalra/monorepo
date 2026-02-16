import { useEffect } from 'react';

/**
 * Ensures theme from localStorage is applied to document on mount and when
 * storage changes (e.g. theme toggled on login page or another tab).
 */
export default function ThemeSync() {
  useEffect(() => {
    const apply = () => {
      const s = localStorage.getItem('theme');
      const dark = s === 'dark' ? true : (s === 'light' ? false : window.matchMedia('(prefers-color-scheme: dark)').matches);
      const root = document.documentElement;
      if (dark) root.classList.add('dark');
      else root.classList.remove('dark');
    };
    apply();
    window.addEventListener('storage', apply);
    return () => window.removeEventListener('storage', apply);
  }, []);
  return null;
}
