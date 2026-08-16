import React, { useState } from 'react';

const APPS = [
  { id: 'people', label: 'People', href: '/app/people/' },
  { id: 'cad', label: 'CAD', href: '/app/cad/' },
  { id: 'food', label: 'Food', href: '/app/food/' },
  { id: 'email', label: 'Email', href: '/app/email/' },
  { id: 'gmail', label: 'Gmail', href: '/app/gmail/' },
  { id: 'gallery', label: 'Gallery', href: '/app/gallery/' },
  { id: 'vacation', label: 'Vacation', href: '/app/vacation/' },
];

export default function AppsMenu({ current }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-sm font-medium text-stone-600 hover:text-stone-900"
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
            className="absolute left-0 z-20 mt-1 min-w-[11rem] rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
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
                      ? 'bg-emerald-50 font-medium text-emerald-800'
                      : 'text-stone-700 hover:bg-stone-50'
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
