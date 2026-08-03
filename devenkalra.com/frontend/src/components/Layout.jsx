import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const Layout = ({ children, menuItems, menuLoading }) => {
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [expandedItems, setExpandedItems] = useState([]);

  const toggleItem = (itemId) => {
    setExpandedItems((prev) =>
      prev.includes(itemId)
        ? prev.filter(id => id !== itemId)
        : [...prev, itemId]
    );
  };

  useEffect(() => {
    setIsMenuOpen(false);
    setExpandedItems([]); // Reset expanded submenus on navigation
  }, [location]);

  // Recursive menu renderer
  const renderMenuItems = (items, level = 1) => {
    const visibleItems = items.filter(item => item.show_in_menu !== false);
    return visibleItems.map((item) => {
      const hasChildren = item.children && item.children.length > 0;
      const isExpanded = expandedItems.includes(item.id);
      
      // Determine link destination
      let toPath = null;
      if (item.page_slug) {
        toPath = `/p/${item.id}/${item.page_slug}`;
      } else if (item.external_url) {
        toPath = item.external_url;
      } else {
        toPath = `/p/${item.id}`;
      }

      const handleClick = (e) => {
        if (hasChildren && (window.innerWidth <= 768 || !toPath)) {
          e.preventDefault();
          toggleItem(item.id);
        }
      };

      const isAbsoluteExternalLink = item.external_url && (item.external_url.startsWith('http://') || item.external_url.startsWith('https://') || item.external_url.startsWith('//'));

      return (
        <li 
          key={item.id} 
          className={hasChildren ? 'menu-item-container dropdown-item-container' : 'menu-item-container'}
        >
          {toPath ? (
            item.external_url ? (
              <a 
                href={toPath} 
                target={isAbsoluteExternalLink ? "_blank" : undefined}
                rel={isAbsoluteExternalLink ? "noopener noreferrer" : undefined}
                className="menu-link dropdown-link"
                onClick={handleClick}
              >
                {item.title} {isAbsoluteExternalLink ? '↗' : ''}
              </a>
            ) : (
              <Link to={toPath} className="menu-link dropdown-link" onClick={handleClick}>
                {item.title} {hasChildren && <span className="menu-arrow" style={{ fontSize: '0.65rem', marginLeft: '0.4rem' }}>{isExpanded ? '▲' : '▼'}</span>}
              </Link>
            )
          ) : (
            <span className="menu-link dropdown-link" onClick={handleClick}>
              {item.title} {hasChildren && <span className="menu-arrow" style={{ fontSize: '0.65rem', marginLeft: '0.4rem' }}>{isExpanded ? '▲' : '▼'}</span>}
            </span>
          )}
          
          {hasChildren && (
            <ul className={`dropdown-menu ${isExpanded ? 'submenu-open' : 'submenu-closed'}`}>
              {renderMenuItems(item.children, level + 1)}
            </ul>
          )}
        </li>
      );
    });
  };

  return (
    <div className="app-container">
      <header className="site-header">
        <div className="header-container">
          <div className="logo-section">
            <Link to="/">devenkalra.com</Link>
          </div>
          
          <button 
            className="menu-toggle-btn" 
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-label="Toggle navigation menu"
          >
            {isMenuOpen ? '✕' : '☰'}
          </button>
          
          <nav className={isMenuOpen ? 'nav-active' : ''}>
            {menuLoading ? (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Loading menu...
              </span>
            ) : (
              <ul className="nav-menu">
                {renderMenuItems(menuItems)}
                <li className="menu-item-container mobile-auth-item">
                  {isAuthenticated ? (
                    <div className="user-badge" style={{ justifyContent: 'center', margin: '0.5rem 0' }}>
                      <span>{user?.username}</span>
                      <button onClick={logout} className="logout-btn">
                        Logout
                      </button>
                    </div>
                  ) : (
                    <Link to="/login" className="menu-link dropdown-link" style={{ justifyContent: 'center' }}>
                      Login
                    </Link>
                  )}
                </li>
              </ul>
            )}
          </nav>
          
          <div className="auth-status-container">
            {isAuthenticated ? (
              <div className="user-badge">
                <span>{user?.username}</span>
                <button onClick={logout} className="logout-btn">
                  Logout
                </button>
              </div>
            ) : (
              <Link 
                to="/login" 
                style={{ 
                  fontFamily: 'var(--font-sans)', 
                  fontSize: '0.8rem', 
                  color: 'var(--text-muted)',
                  textDecoration: 'none'
                }}
              >
                Login
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="main-content">
        {children}
      </main>

      <footer className="site-footer">
        <div className="footer-container">
          <p>© {new Date().getFullYear()} Deven Kalra 💬
            <a href="/p/contact" target="_blank" rel="noopener noreferrer">Want a site like this?</a></p>
        </div>
      </footer>
    </div>
  );
};
