import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Layout } from './components/Layout';
import { Home } from './views/Home';
import { PageView } from './views/PageView';
import { Login } from './views/Login';
import { BlogCatalog } from './views/BlogCatalog';
import { BlogPostDetail } from './views/BlogPostDetail';
import { GithubCallback } from './views/GithubCallback';
import { GoogleCallback } from './views/GoogleCallback';
import { SocialLoginModal } from './components/SocialLoginModal';

function AppShell() {
  const { token, isAuthenticated, user, loading: authLoading } = useAuth();
  const [menuItems, setMenuItems] = useState([]);
  const [menuLoading, setMenuLoading] = useState(true);

  // Refetch menu whenever auth changes so role-gated items (e.g. Apps) update.
  useEffect(() => {
    if (authLoading) return;

    let cancelled = false;
    const fetchMenu = async () => {
      setMenuLoading(true);
      try {
        const headers = { Accept: 'application/json' };
        if (token) headers.Authorization = `Token ${token}`;

        const response = await fetch('/api/menu/', {
          headers,
          credentials: 'include',
        });
        if (!response.ok) return;
        const data = await response.json();
        if (!cancelled) setMenuItems(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('Error fetching menu:', err);
      } finally {
        if (!cancelled) setMenuLoading(false);
      }
    };

    fetchMenu();
    return () => {
      cancelled = true;
    };
  }, [authLoading, token, isAuthenticated, user?.role]);

  return (
    <>
      <SocialLoginModal />
      <Router>
        <Layout menuItems={menuItems} menuLoading={menuLoading}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/blog" element={<BlogCatalog />} />
            <Route path="/blog/:slug" element={<BlogPostDetail />} />
            {/* Legacy aliases */}
            <Route path="/articles" element={<BlogCatalog />} />
            <Route path="/articles/:slug" element={<BlogPostDetail />} />
            <Route path="/p/:menuItemId/:slug?" element={<PageView menuItems={menuItems} />} />
            <Route path="/login" element={<Login />} />
            <Route path="/login/google/callback" element={<GoogleCallback />} />
            <Route path="/login/github/callback" element={<GithubCallback />} />
            <Route
              path="*"
              element={
                <div style={{ padding: '3rem 0', textAlign: 'center' }}>
                  <h1>404 Page Not Found</h1>
                  <p>The page you are looking for does not exist.</p>
                </div>
              }
            />
          </Routes>
        </Layout>
      </Router>
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
