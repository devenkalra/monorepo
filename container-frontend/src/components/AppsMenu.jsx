import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const APPS = [
  { id: 'people', label: 'People', to: '/people-app' },
  { id: 'cad', label: 'CAD', to: '/cad-app' },
  { id: 'food', label: 'Food', to: '/food-app' },
  { id: 'email', label: 'Email', href: '/email-app/' },
  { id: 'gmail', label: 'Gmail', href: '/gmail-app/' },
  { id: 'gallery', label: 'Gallery', href: '/app/gallery/' },
  { id: 'vacation', label: 'Vacation', href: '/app/vacation/' },
  { id: 'trips', label: 'Trips', href: '/app/trips/' },
];

export default function AppsMenu({ current }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        Apps
        <svg className="h-3.5 w-3.5 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="absolute left-0 z-20 mt-1 min-w-[11rem] rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-600 dark:bg-gray-800"
          >
            {APPS.map((app) => {
              const active = app.id === current;
              const className = `block px-3 py-2 text-sm ${
                active
                  ? 'bg-gray-100 font-medium text-blue-600 dark:bg-gray-700 dark:text-blue-400'
                  : 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700'
              }`;
              if (app.href) {
                return (
                  <a
                    key={app.id}
                    href={app.href}
                    role="menuitem"
                    aria-current={active ? 'page' : undefined}
                    onClick={() => setOpen(false)}
                    className={className}
                  >
                    {app.label}
                  </a>
                );
              }
              return (
                <Link
                  key={app.id}
                  to={app.to}
                  role="menuitem"
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setOpen(false)}
                  className={className}
                >
                  {app.label}
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
