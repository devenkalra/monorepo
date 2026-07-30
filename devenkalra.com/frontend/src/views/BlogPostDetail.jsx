import { useState, useEffect } from 'react';
import { useParams, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { MarkdownBody } from '../components/MarkdownBody';

export const BlogPostDetail = () => {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { isAuthenticated, user, logout, openSocialLoginModal } = useAuth();

  const [post, setPost] = useState(null);
  const [comments, setComments] = useState([]);
  const [relatedPosts, setRelatedPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Comment form state
  const [content, setContent] = useState('');
  const [websiteUrl, setWebsiteUrl] = useState(''); // Honeypot spam field
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [commentsExpanded, setCommentsExpanded] = useState(false);
  const [loginError, setLoginError] = useState('');

  // Auto-expand comments if returning from GitHub auth callback redirect
  useEffect(() => {
    if (window.location.search.includes('comments=true')) {
      setCommentsExpanded(true);
    }
  }, []);

  // Fetch BlogPost details and approved comments
  useEffect(() => {
    const fetchPostAndComments = async () => {
      setLoading(true);
      setError('');
      setSubmitSuccess(false);
      setSubmitError('');
      
      try {
        // Fetch post details (attaching preview token if available)
        const postUrl = token ? `/api/blog/posts/${slug}/?token=${token}` : `/api/blog/posts/${slug}/`;
        const postRes = await fetch(postUrl);
        if (!postRes.ok) {
          if (postRes.status === 404) {
            setError('Article not found.');
          } else {
            setError('Failed to load blog post.');
          }
          setLoading(false);
          return;
        }
        const postData = await postRes.json();
        setPost(postData);

        // Fetch approved comments
        const commentsRes = await fetch(`/api/blog/posts/${slug}/comments/`);
        if (commentsRes.ok) {
          const commentsData = await commentsRes.json();
          setComments(commentsData);
        }

        // Fetch related posts (client-side matching from general list)
        const allPostsRes = await fetch('/api/blog/posts/');
        if (allPostsRes.ok) {
          const allPosts = await allPostsRes.json();
          
          // Filter out the current post
          const otherPosts = allPosts.filter(p => p.slug !== slug);
          
          // Calculate tag overlaps
          const currentTagIds = new Set(postData.tags || []);
          const scored = otherPosts.map(p => {
            let score = 0;
            if (p.category === postData.category) {
              score += 2; // Category match bonus
            }
            if (p.tags) {
              p.tags.forEach(tId => {
                if (currentTagIds.has(tId)) score += 3; // Tag match bonus
              });
            }
            return { post: p, score };
          });

          // Sort by score descending, then date descending
          scored.sort((a, b) => {
            if (b.score !== a.score) return b.score - a.score;
            return new Date(b.post.publish_date || b.post.created_at) - new Set(a.post.publish_date || a.post.created_at);
          });

          // Select top 3 related posts (with score > 0 to ensure relevance, or fallback to latest if no matches)
          const chosen = scored.slice(0, 3).map(s => s.post);
          setRelatedPosts(chosen);
        }
      } catch (err) {
        console.error("Error loading blog details:", err);
        setError('Network error occurred.');
      } finally {
        setLoading(false);
      }
    };

    fetchPostAndComments();
  }, [slug, token]);

  // Handle comment submission
  const handleCommentSubmit = async (e) => {
    e.preventDefault();
    setSubmitLoading(true);
    setSubmitError('');

    const payload = {
      content: content,
      website_url: websiteUrl // Send the honeypot value to backend
    };

    try {
      // Fetch CSRF Token
      let csrfToken = null;
      try {
        const csrfRes = await fetch('/api/auth/csrf/', { credentials: 'include' });
        if (csrfRes.ok) {
          const csrfData = await csrfRes.json();
          csrfToken = csrfData.csrfToken;
        }
      } catch (csrfErr) {
        console.error("Failed to fetch CSRF token for comment:", csrfErr);
      }

      const headers = {
        'Content-Type': 'application/json',
      };
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }

      const response = await fetch(`/api/blog/posts/${slug}/comments/`, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload),
        credentials: 'include'
      });

      if (response.ok) {
        setSubmitSuccess(true);
        setContent('');
        setWebsiteUrl('');
      } else {
        const errorData = await response.json();
        setSubmitError(errorData.detail || 'Failed to submit comment. Please check your fields.');
      }
    } catch (err) {
      console.error("Comment submission error:", err);
      setSubmitError('Network error. Please try again.');
    } finally {
      setSubmitLoading(false);
    }
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

  // Get initial character for comment avatar
  const getAvatarInitials = (name) => {
    if (!name) return '?';
    return name.charAt(0).toUpperCase();
  };

  if (loading) {
    return <div className="text-center" style={{ padding: '6rem 0', color: 'var(--text-muted)' }}>Loading article...</div>;
  }

  if (error) {
    return (
      <div className="text-center" style={{ padding: '6rem 2rem' }}>
        <h2 style={{ fontWeight: 400, marginBottom: '1rem' }}>{error}</h2>
        <Link to="/articles" className="editorial-button" style={{ display: 'inline-block', width: 'auto' }}>
          Back to Articles
        </Link>
      </div>
    );
  }

  if (!post) return null;

  return (
    <article className="blog-post-detail">
      {/* Breadcrumbs */}
      <div className="breadcrumbs">
        <Link to="/">Home</Link>
        <span className="breadcrumbs-separator">/</span>
        <Link to="/articles">Articles</Link>
        <span className="breadcrumbs-separator">/</span>
        <span className="current">{post.title}</span>
      </div>



      {/* Header Info */}
      <header className="blog-post-header">
        {!post.is_published && (
          <div style={{
            backgroundColor: token ? '#f0fdf4' : '#fffbeb',
            border: token ? '1px solid #15803d' : '1px solid #d97706',
            color: token ? '#166534' : '#b45309',
            padding: '0.75rem 1rem',
            marginBottom: '1.5rem',
            borderRadius: '4px',
            fontFamily: 'var(--font-sans)',
            fontSize: '0.85rem',
            fontWeight: 500
          }}>
            {token ? (
              <span>📖 PREVIEW MODE — You are viewing an unpublished draft shareable preview. Feel free to read and leave comments!</span>
            ) : (
              <span>⚠️ DRAFT MODE — This post is unpublished. It is only visible to you as an administrator.</span>
            )}
          </div>
        )}
        <h1 style={{ fontSize: '2.8rem', lineHeight: '1.25', marginBottom: '1rem' }}>{post.title}</h1>
        
        <div className="blog-post-meta">
          {post.category_name && (
            <span className="blog-post-category-badge">{post.category_name}</span>
          )}
          {post.category_name && <span className="meta-separator">•</span>}
          <span>{formatDate(post.publish_date || post.created_at)}</span>
          <span className="meta-separator">•</span>
          <span>{calculateReadingTime(post.content)} min read</span>
        </div>
      </header>

      {/* Article Content */}
      <section className="blog-post-content markdown-body">
        {post.render_as_html ? (
          <div dangerouslySetInnerHTML={{ __html: post.content }} />
        ) : (
          <MarkdownBody>{post.content}</MarkdownBody>
        )}
      </section>

      {/* Tags Footer list */}
      {post.tags_detail && post.tags_detail.length > 0 && (
        <div className="blog-post-tags">
          <span>Tags:</span>
          {post.tags_detail.map(tag => (
            <Link key={tag.id} to={`/articles?tag=${tag.slug}`} className="tag-btn" style={{ textDecoration: 'none' }}>
              {tag.name}
            </Link>
          ))}
        </div>
      )}

      {/* Comments Section */}
      <section className="blog-comments-section" style={{ marginBottom: '3rem' }}>
        <button 
          onClick={() => setCommentsExpanded(!commentsExpanded)}
          className="comments-toggle-btn"
          style={{
            background: 'none',
            border: 'none',
            width: '100%',
            textAlign: 'left',
            padding: '1.25rem 0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            cursor: 'pointer',
            fontFamily: 'var(--font-serif)',
            fontSize: '1.6rem',
            color: 'var(--text-color)',
            borderBottom: '1px solid var(--border-color)',
            marginBottom: commentsExpanded ? '1.5rem' : '0',
            transition: 'var(--transition-smooth)'
          }}
          aria-expanded={commentsExpanded}
        >
          <span>Comments ({comments.length})</span>
          <span style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>
            {commentsExpanded ? 'Hide Comments ▲' : 'Show Comments ▼'}
          </span>
        </button>

        {commentsExpanded && (
          <div className="comments-expandable-content" style={{ marginTop: '1rem' }}>
            {/* List of comments */}
            <div className="comments-list">
              {comments.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.95rem' }}>
                  No comments yet. Be the first to share your thoughts!
                </p>
              ) : (
                comments.map(comment => (
                  <div key={comment.id} className="comment-card">
                    <div className="comment-header">
                      <div className="comment-author-info">
                        <div className="comment-avatar">
                          {getAvatarInitials(comment.author_name)}
                        </div>
                        <div>
                          <div className="comment-author-name">{comment.author_name}</div>
                          <div className="comment-date">{formatDate(comment.created_at)}</div>
                        </div>
                      </div>
                    </div>
                    <div className="comment-content">
                      {comment.content}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Add Comment Form */}
            <div className="comment-form-wrapper" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem', marginTop: '1.5rem' }}>
              <h4 style={{ marginBottom: '1rem' }}>Leave a Comment</h4>
              
              {!isAuthenticated ? (
                <div style={{ padding: '1.5rem', background: 'var(--accent-light, #f4efe6)', borderRadius: '4px', textAlign: 'center' }}>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-color)', marginBottom: '1.2rem' }}>
                    You must sign in temporarily with a social account before you can post comments.
                  </p>
                  <button 
                    type="button" 
                    onClick={() => openSocialLoginModal()} 
                    className="editorial-button"
                    style={{ width: '240px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', margin: '0 auto' }}
                  >
                    🔑 Sign In to Comment
                  </button>
                </div>
              ) : (
                <form onSubmit={handleCommentSubmit}>
                  {submitError && (
                    <div className="error-message" style={{ marginBottom: '1rem' }}>
                      ✕ {submitError}
                    </div>
                  )}
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--accent-light, #f4efe6)', padding: '0.6rem 1rem', borderRadius: '4px', marginBottom: '1.2rem', fontFamily: 'var(--font-sans)', fontSize: '0.82rem' }}>
                    <span style={{ color: 'var(--text-color)', fontWeight: 500 }}>
                      ✍️ Posting as: <strong>{user?.username}</strong> ({user?.email})
                    </span>
                    <button 
                      type="button" 
                      onClick={logout} 
                      style={{ background: 'none', border: 'none', color: '#c0392b', cursor: 'pointer', fontSize: '0.8rem', textDecoration: 'underline', padding: 0 }}
                    >
                      Sign Out
                    </button>
                  </div>

                  {/* Spam bot Honeypot field - hidden with CSS, absolute positioned */}
                  <div className="honeypot-field">
                    <label htmlFor="website_url">Website URL (leave empty)</label>
                    <input
                      id="website_url"
                      type="text"
                      name="website_url"
                      value={websiteUrl}
                      onChange={(e) => setWebsiteUrl(e.target.value)}
                      autoComplete="off"
                      tabIndex="-1"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="comment-content" className="form-label" style={{ display: 'none' }}>Comment *</label>
                    <textarea
                      id="comment-content"
                      className="form-input"
                      required
                      rows="4"
                      placeholder="Share your thoughts..."
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      style={{ resize: 'vertical', fontFamily: 'var(--font-serif)', fontSize: '0.95rem' }}
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={submitLoading}
                    className="editorial-button"
                    style={{ width: 'auto', display: 'inline-block', marginTop: '0.5rem' }}
                  >
                    {submitLoading ? 'Submitting...' : 'Post Comment'}
                  </button>
                </form>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Related Posts */}
      {relatedPosts.length > 0 && (
        <section className="related-posts-section">
          <h3>Related Articles</h3>
          <div className="cards-grid" style={{ marginTop: '1rem' }}>
            {relatedPosts.map(related => (
              <Link to={`/articles/${related.slug}`} key={related.id} className="editorial-card" style={{ textDecoration: 'none' }}>
                <span className="blog-card-category" style={{ fontSize: '0.65rem' }}>{related.category_name}</span>
                <h4 className="card-title" style={{ fontSize: '1.1rem', margin: '0.25rem 0 0.5rem 0' }}>{related.title}</h4>
                <p className="card-content" style={{ fontSize: '0.85rem', color: 'var(--text-muted)', WebkitLineClamp: 2, display: '-webkit-box', WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {related.summary || 'Read full article...'}
                </p>
                <div className="card-meta" style={{ margin: 0, fontSize: '0.75rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
                  {formatDate(related.publish_date || related.created_at)}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </article>
  );
};
