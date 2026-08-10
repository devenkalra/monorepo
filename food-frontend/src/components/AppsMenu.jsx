import React, { useState } from 'react';

const APPS = [
  { id: 'people', label: 'People', href: '/people-app/' },
  { id: 'cad', label: 'CAD', href: '/cad-app/' },
  { id: 'food', label: 'Food', href: '/food-app/' },
  { id: 'email', label: 'Email', href: '/email-app/' },
  { id: 'gmail', label: 'Gmail', href: '/gmail-app/' },
];

export default function AppsMenu({ current }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
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
              return (
                <a
                  key={app.id}
                  href={app.href}
                  role="menuitem"
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setOpen(false)}
                  className={`block px-3 py-2 text-sm ${
                    active
                      ? 'bg-gray-100 font-medium text-amber-600 dark:bg-gray-700 dark:text-amber-400'
                      : 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700'
                  }`}
                >
                  {app.label}
                </a>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
