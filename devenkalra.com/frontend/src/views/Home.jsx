import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

export const Home = () => {
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchHomeContent = async () => {
      try {
        const response = await fetch('/api/pages/who-am-i/');
        if (response.ok) {
          const data = await response.json();
          setPage(data);
        } else {
          setError('Failed to load page content.');
        }
      } catch (err) {
        console.error("Error fetching home content:", err);
        setError('Network error occurred.');
      } finally {
        setLoading(false);
      }
    };

    fetchHomeContent();
  }, []);

  if (loading) {
    return <div className="text-center" style={{ padding: '3rem 0' }}>Loading...</div>;
  }

  if (error) {
    return <div className="text-center error-message" style={{ padding: '3rem 0' }}>{error}</div>;
  }

  return (
    <article className="markdown-body">
      <ReactMarkdown>{page?.content}</ReactMarkdown>
    </article>
  );
};
