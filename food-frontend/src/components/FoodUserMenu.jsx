import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';

export default function FoodUserMenu() {
  const { user, logout } = useAuth();
  const [showMenu, setShowMenu] = useState(false);

  if (!user) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setShowMenu(!showMenu)}
        className="flex items-center space-x-2 px-3 py-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
      >
        <div className="w-8 h-8 rounded-full bg-amber-600 flex items-center justify-center text-white font-semibold text-sm">
          {user?.email?.[0]?.toUpperCase() || 'U'}
        </div>
        <span className="text-sm font-medium hidden sm:inline text-gray-900 dark:text-gray-100">{user?.email}</span>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {showMenu && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
          <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg z-20 border border-gray-200 dark:border-gray-700">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{user?.username || 'User'}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user?.email}</p>
            </div>
            <div className="border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => { setShowMenu(false); logout(); }}
                className="w-full text-left px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-b-lg transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
