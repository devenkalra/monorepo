import React, { useEffect, useState } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import ThemeSync from './ThemeSync';
import ThemeToggle from './ThemeToggle';
import FoodUserMenu from './FoodUserMenu';
import FoodSpotsList from './FoodSpotsList';
import FoodSpotDetail from './FoodSpotDetail';
import FoodSpotEdit from './FoodSpotEdit';
import FoodsList from './FoodsList';
import FoodDetail from './FoodDetail';
import FoodEdit from './FoodEdit';
import SpotListsList from './SpotListsList';
import SpotListDetail from './SpotListDetail';
import SpotListEdit from './SpotListEdit';
import FoodListsList from './FoodListsList';
import FoodListDetail from './FoodListDetail';
import FoodListEdit from './FoodListEdit';
import HelpModal from './HelpModal';
import ProfileEdit from './ProfileEdit';
import api, { ensureCsrfCookie, AUTH_EXPIRED_EVENT } from '../services/api';

const API_BASE = '/api/food';

export default function FoodApp() {
  const { user } = useAuth();
  const location = useLocation();
  const [showSessionExpiredModal, setShowSessionExpiredModal] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    ensureCsrfCookie();
  }, []);

  useEffect(() => {
    const onAuthExpired = () => setShowSessionExpiredModal(true);
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
  }, []);

  const header = (
    <header className="mb-4 border-b border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Food</h1>
          <nav className="flex items-center gap-2 text-sm">
            <a href="/people-app/" className="font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
              People
            </a>
            <span className="text-gray-400">|</span>
            <a href="/cad-app/" className="font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
              CAD
            </a>
            <span className="text-gray-400">|</span>
            <button onClick={() => setShowHelp(true)} className="font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">Help</button>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <FoodUserMenu />
        </div>
      </div>
      <nav className="flex items-center gap-2 px-4 pb-3 text-sm text-gray-600 dark:text-gray-400">
        <Link
          to="/"
          className={`font-medium ${location.pathname === '/' ? 'text-amber-600 dark:text-amber-400' : 'hover:text-gray-900 dark:hover:text-gray-100'}`}
        >
          Spots
        </Link>
        <span className="text-gray-300 dark:text-gray-600">|</span>
        <Link
          to="/foods"
          className={`font-medium ${location.pathname.startsWith('/foods') && !location.pathname.startsWith('/food-lists') ? 'text-amber-600 dark:text-amber-400' : 'hover:text-gray-900 dark:hover:text-gray-100'}`}
        >
          Foods
        </Link>
        {user && (
          <>
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <Link
              to="/spot-lists"
              className={`font-medium ${location.pathname.startsWith('/spot-lists') ? 'text-amber-600 dark:text-amber-400' : 'hover:text-gray-900 dark:hover:text-gray-100'}`}
            >
              Spot Lists
            </Link>
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <Link
              to="/food-lists"
              className={`font-medium ${location.pathname.startsWith('/food-lists') ? 'text-amber-600 dark:text-amber-400' : 'hover:text-gray-900 dark:hover:text-gray-100'}`}
            >
              Food Lists
            </Link>
          </>
        )}
      </nav>
    </header>
  );

  return (
    <>
      <ThemeSync />
      <HelpModal open={showHelp} onClose={() => setShowHelp(false)} />
      {showSessionExpiredModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border border-gray-200 dark:border-gray-600 min-w-[320px]">
            <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Session Expired</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Your session has expired. Please log in again to continue.</p>
            <div className="flex justify-end">
              <button
                onClick={() => {
                  setShowSessionExpiredModal(false);
                  window.location.href = window.location.origin + '/login/?next=' + encodeURIComponent('/food-app/');
                }}
                className="px-4 py-2 rounded bg-amber-600 hover:bg-amber-700 text-white"
              >
                Log in again
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
        <div className="mx-auto w-full max-w-4xl p-4 pb-24">
          {header}
          <Routes>
            <Route path="/profile" element={user ? <ProfileEdit /> : <Navigate to="/" replace />} />
            <Route path="/" element={<FoodSpotsList apiBase={API_BASE} user={user} />} />
            <Route path="/spot/create" element={user ? <FoodSpotEdit apiBase={API_BASE} /> : <Navigate to={`/login/?next=${encodeURIComponent(typeof window !== 'undefined' ? window.location.pathname : '/food-app/spot/create')}`} replace />} />
            <Route path="/spot/:id" element={<FoodSpotDetail apiBase={API_BASE} user={user} />} />
            <Route path="/spot/:id/edit" element={user ? <FoodSpotEdit apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/spot-lists" element={user ? <SpotListsList apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/spot-lists/create" element={user ? <SpotListEdit apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/spot-lists/:id" element={user ? <SpotListDetail apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/spot-lists/:id/edit" element={user ? <SpotListEdit apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/foods" element={<FoodsList apiBase={API_BASE} user={user} />} />
            <Route path="/food/create" element={user ? <FoodEdit apiBase={API_BASE} /> : <Navigate to={`/login/?next=${encodeURIComponent(typeof window !== 'undefined' ? window.location.pathname : '/food-app/food/create')}`} replace />} />
            <Route path="/food/:id" element={<FoodDetail apiBase={API_BASE} user={user} />} />
            <Route path="/food/:id/edit" element={user ? <FoodEdit apiBase={API_BASE} /> : <Navigate to="/foods" replace />} />
            <Route path="/food-lists" element={user ? <FoodListsList apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/food-lists/create" element={user ? <FoodListEdit apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/food-lists/:id" element={user ? <FoodListDetail apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="/food-lists/:id/edit" element={user ? <FoodListEdit apiBase={API_BASE} /> : <Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </>
  );
}
