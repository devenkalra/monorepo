import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

export const BlogCatalog = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [posts, setPosts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Extract query parameters from URL search params
  const searchQuery = searchParams.get('q') || '';
  const selectedCategory = searchParams.get('category') || '';
  const selectedTag = searchParams.get('tag') || '';

  // Local search text state to avoid searching on every keystroke
  const [searchText, setSearchText] = useState(searchQuery);
  const [prevSearchQuery, setPrevSearchQuery] = useState(searchQuery);

  // Sync local search text state if URL query changes externally
  if (searchQuery !== prevSearchQuery) {
    setPrevSearchQuery(searchQuery);
    setSearchText(searchQuery);
  }

  // Fetch categories and tags once on mount
  useEffect(() => {
    const fetchMetadata = async () => {
      try {
        const [categoriesRes, tagsRes] = await Promise.all([
          fetch('/api/blog/categories/'),
          fetch('/api/blog/tags/')
        ]);

        if (categoriesRes.ok) {
          const catData = await categoriesRes.json();
          setCategories(catData);
        }
        if (tagsRes.ok) {
          const tagData = await tagsRes.json();
          setTags(tagData);
        }
      } catch (err) {
        console.error("Error fetching filter metadata:", err);
      }
    };

    fetchMetadata();
  }, []);

  // Fetch blog posts matching active filters
  useEffect(() => {
    const fetchPosts = async () => {
      setLoading(true);
      setError('');
      try {
        const queryParams = new URLSearchParams();
        if (searchQuery) queryParams.append('q', searchQuery);
        if (selectedCategory) queryParams.append('category', selectedCategory);
        if (selectedTag) queryParams.append('tag', selectedTag);

        const response = await fetch(`/api/blog/posts/?${queryParams.toString()}`);
        if (response.ok) {
          const data = await response.json();
          setPosts(data);
        } else {
          setError('Failed to fetch blog posts.');
        }
      } catch (err) {
        console.error("Error fetching blog posts:", err);
        setError('Network error occurred.');
      } finally {
        setLoading(false);
      }
    };

    fetchPosts();
  }, [searchQuery, selectedCategory, selectedTag]);

  // Update URL parameters
  const updateParams = (key, value) => {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    setSearchParams(newParams);
  };

  // Handle search submit
  const handleSearchSubmit = (e) => {
    e.preventDefault();
    updateParams('q', searchText);
  };

  // Reset all filters
  const resetFilters = () => {
    setSearchParams({});
    setSearchText('');
  };

  // Estimate reading time in minutes
  const calculateReadingTime = (text) => {
    if (!text) return 1;
    const words = text.trim().split(/\s+/).length;
    const minutes = Math.ceil(words / 200);
    return minutes;
  };

  // Format date nicely
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  return (
    <div className="blog-catalog-container">
      <div className="breadcrumbs">
        <Link to="/">Home</Link>
        <span className="breadcrumbs-separator">/</span>
        <span className="current">Articles</span>
      </div>

      <h1 style={{ marginBottom: '0.5rem' }}>Writing & Musings</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2.5rem', fontFamily: 'var(--font-serif)', fontStyle: 'italic' }}>
        Thoughts, project diaries, and explorations in woodworking, photography, music, and software.
      </p>

      <div className="blog-layout">
        {/* Sidebar Filters */}
        <aside className="blog-sidebar">
          {/* Search Box */}
          <form onSubmit={handleSearchSubmit} className="blog-search-box">
            <h4 style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: 'var(--text-muted)',
              marginBottom: '0.5rem',
              fontWeight: 600
            }}>Search Posts</h4>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input
                type="text"
                className="form-input"
                placeholder="Type keywords..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                style={{ padding: '0.6rem 0.8rem', fontSize: '0.85rem' }}
              />
              <button
                type="submit"
                className="editorial-button"
                style={{
                  marginTop: 0,
                  width: 'auto',
                  padding: '0.6rem 1rem',
                  fontSize: '0.8rem'
                }}
              >
                Go
              </button>
            </div>
          </form>

          {/* Categories Filter */}
          <div className="blog-filter-section">
            <h4>Categories</h4>
            <div className="category-list">
              <button
                className={`category-btn ${!selectedCategory ? 'active' : ''}`}
                onClick={() => updateParams('category', '')}
              >
                All Categories
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.id}
                  className={`category-btn ${selectedCategory === cat.slug ? 'active' : ''}`}
                  onClick={() => updateParams('category', cat.slug)}
                >
                  {cat.name}
                </button>
              ))}
            </div>
          </div>

          {/* Tags Filter */}
          <div className="blog-filter-section">
            <h4>Tags</h4>
            <div className="tag-cloud">
              {tags.map((tag) => (
                <button
                  key={tag.id}
                  className={`tag-btn ${selectedTag === tag.slug ? 'active' : ''}`}
                  onClick={() => updateParams('tag', selectedTag === tag.slug ? '' : tag.slug)}
                >
                  {tag.name}
                </button>
              ))}
            </div>
          </div>

          {/* Reset Filters */}
          {(searchQuery || selectedCategory || selectedTag) && (
            <button className="reset-filters-btn" onClick={resetFilters}>
              Reset Active Filters
            </button>
          )}
        </aside>

        {/* Blog Posts Grid */}
        <main className="blog-main">
          {loading ? (
            <div className="text-center" style={{ padding: '4rem 0', color: 'var(--text-muted)' }}>
              Loading posts...
            </div>
          ) : error ? (
            <div className="text-center error-message" style={{ padding: '4rem 0' }}>
              {error}
            </div>
          ) : posts.length === 0 ? (
            <div className="text-center" style={{ padding: '4rem 2rem', border: '1px dashed var(--border-color)' }}>
              <h3 style={{ fontWeight: 400, marginBottom: '0.5rem' }}>No articles found</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', marginBottom: '1.5rem' }}>
                We couldn't find any posts matching your selected filters or search keywords.
              </p>
              <button
                onClick={resetFilters}
                className="editorial-button"
                style={{ width: 'auto', display: 'inline-block', margin: 0 }}
              >
                Reset All Filters
              </button>
            </div>
          ) : (
            <div className="blog-posts-grid">
              {posts.map((post) => (
                <Link to={`/articles/${post.slug}`} key={post.id} className="blog-card">
                  <div className="blog-card-image-wrapper">
                    {post.cover_image ? (
                      <img
                        src={post.cover_image}
                        alt={post.title}
                        className="blog-card-image"
                        loading="lazy"
                      />
                    ) : (
                      <div className="blog-card-placeholder">
                        <span>{post.category_name || 'Musing'}</span>
                      </div>
                    )}
                  </div>
                  <div className="blog-card-body">
                    <span className="blog-card-category">{post.category_name || 'General'}</span>
                    <h3 className="blog-card-title">{post.title}</h3>
                    <p className="blog-card-excerpt">{post.summary || 'Click to read full article...'}</p>
                    <div className="blog-card-meta">
                      <span>{formatDate(post.publish_date || post.created_at)}</span>
                      <span>{calculateReadingTime(post.content)} min read</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
