import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getLoginUrl } from '../utils/apiUrl';
import AppsMenu from './AppsMenu';
import GalleryEditor from './GalleryEditor';
import GalleryList from './GalleryList';

export default function GalleryApp() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return <div className="p-8 text-center text-stone-500">Loading…</div>;
  }

  if (!user) {
    window.location.replace(getLoginUrl('/app/gallery/'));
    return null;
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <AppsMenu current="gallery" />
          <span className="text-sm font-semibold text-stone-800">Gallery</span>
          <div className="ml-auto flex items-center gap-3 text-sm text-stone-600">
            <span className="hidden sm:inline">{user.displayname || user.email}</span>
            <button type="button" className="hover:text-stone-900" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<GalleryList />} />
        <Route path="/g/:id" element={<GalleryEditor />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
