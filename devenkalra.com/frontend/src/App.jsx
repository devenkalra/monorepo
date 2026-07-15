import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { Layout } from './components/Layout';
import { Home } from './views/Home';
import { PageView } from './views/PageView';
import { Login } from './views/Login';
import { BlogCatalog } from './views/BlogCatalog';
import { BlogPostDetail } from './views/BlogPostDetail';
import { GithubCallback } from './views/GithubCallback';
import { SocialLoginModal } from './components/SocialLoginModal';

function App() {
  const [menuItems, setMenuItems] = useState([]);
  const [menuLoading, setMenuLoading] = useState(true);

  // Fetch the menu structure once globally on application mount
  useEffect(() => {
    const fetchMenu = async () => {
      try {
        const response = await fetch('/api/menu/');
        if (response.ok) {
          const data = await response.json();
          setMenuItems(data);
        }
      } catch (err) {
        console.error("Error fetching menu:", err);
      } finally {
        setMenuLoading(false);
      }
    };

    fetchMenu();
  }, []);

  return (
    <AuthProvider>
      <SocialLoginModal />
      <Router>
        <Layout menuItems={menuItems} menuLoading={menuLoading}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/articles" element={<BlogCatalog />} />
            <Route path="/articles/:slug" element={<BlogPostDetail />} />
            <Route path="/p/:menuItemId/:slug?" element={<PageView menuItems={menuItems} />} />
            <Route path="/login" element={<Login />} />
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
    </AuthProvider>
  );
}

export default App;
