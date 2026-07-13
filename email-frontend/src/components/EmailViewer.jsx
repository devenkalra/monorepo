import React, { useState, useEffect } from 'react';
import api from '../services/api';

function EmailViewer() {
  const [emails, setEmails] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [filters, setFilters] = useState({
    account: '',
    from: '',
    to: '',
    subject: '',
    q: '',
    has_attachments: '',
    date_from: '',
    date_to: '',
  });
  const [sortBy, setSortBy] = useState('date');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAccounts();
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [filters, sortBy]);

  useEffect(() => {
    fetchEmails();
  }, [currentPage, filters, sortBy]);

  const fetchAccounts = async () => {
    try {
      const resp = await api.fetch('/api/mail/accounts/');
      if (!resp.ok) {
        console.error('Failed to fetch accounts:', resp.status, resp.statusText);
        return;
      }
      const data = await resp.json();
      // Handle paginated response
      const accountsList = data.results || data;
      setAccounts(Array.isArray(accountsList) ? accountsList : []);
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
      setAccounts([]);
    }
  };

  const fetchEmailDetail = async (emailId) => {
    setLoadingDetail(true);
    try {
      const resp = await api.fetch(`/api/mail/emails/${emailId}/`);
      if (!resp.ok) {
        console.error('Failed to fetch email detail:', resp.status);
        return null;
      }
      const data = await resp.json();
      return data;
    } catch (error) {
      console.error('Failed to fetch email detail:', error);
      return null;
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleEmailClick = async (email) => {
    const fullEmail = await fetchEmailDetail(email.id);
    if (fullEmail) {
      setSelectedEmail(fullEmail);
    }
  };

  const fetchEmails = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('page', currentPage.toString());
      params.append('page_size', pageSize.toString());
      params.append('sort_by', sortBy);
      
      if (filters.account) params.append('account', filters.account);
      if (filters.from) params.append('from', filters.from);
      if (filters.to) params.append('to', filters.to);
      if (filters.subject) params.append('subject', filters.subject);
      if (filters.q) params.append('q', filters.q);
      if (filters.has_attachments) params.append('has_attachments', filters.has_attachments);
      if (filters.date_from) params.append('date_from', filters.date_from);
      if (filters.date_to) params.append('date_to', filters.date_to);

      const resp = await api.fetch(`/api/mail/emails/?${params.toString()}`);
      const data = await resp.json();
      
      setEmails(data.results || []);
      setTotalCount(data.count || 0);
      setTotalPages(data.total_pages || 0);
    } catch (error) {
      console.error('Failed to fetch emails:', error);
      setEmails([]);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const truncate = (str, maxLen) => {
    if (!str) return '';
    return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
  };

  return (
    <div>
      <div className="mb-6">
          
          {/* Search and Filters */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 space-y-3">
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="Search emails..."
                value={filters.q}
                onChange={(e) => setFilters(prev => ({ ...prev, q: e.target.value }))}
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              >
                <option value="date">Newest First</option>
                <option value="date_asc">Oldest First</option>
                <option value="subject">Subject A-Z</option>
                <option value="from">From A-Z</option>
              </select>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <select
                value={filters.account}
                onChange={(e) => setFilters(prev => ({ ...prev, account: e.target.value }))}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              >
                <option value="">All Accounts</option>
                {accounts.map(acc => (
                  <option key={acc.id} value={acc.id}>{acc.name}</option>
                ))}
              </select>
              
              <input
                type="text"
                placeholder="From..."
                value={filters.from}
                onChange={(e) => setFilters(prev => ({ ...prev, from: e.target.value }))}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              />
              
              <input
                type="text"
                placeholder="To..."
                value={filters.to}
                onChange={(e) => setFilters(prev => ({ ...prev, to: e.target.value }))}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              />
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input
                type="text"
                placeholder="Subject..."
                value={filters.subject}
                onChange={(e) => setFilters(prev => ({ ...prev, subject: e.target.value }))}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              />
              
              <input
                type="date"
                placeholder="From date"
                value={filters.date_from}
                onChange={(e) => setFilters(prev => ({ ...prev, date_from: e.target.value }))}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              />
              
              <input
                type="date"
                placeholder="To date"
                value={filters.date_to}
                onChange={(e) => setFilters(prev => ({ ...prev, date_to: e.target.value }))}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
              />
            </div>
            
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={filters.has_attachments === 'true'}
                  onChange={(e) => setFilters(prev => ({ 
                    ...prev, 
                    has_attachments: e.target.checked ? 'true' : '' 
                  }))}
                  className="rounded"
                />
                Has Attachments
              </label>
              
              {(filters.q || filters.from || filters.to || filters.subject || filters.account || filters.date_from || filters.date_to || filters.has_attachments) && (
                <button
                  onClick={() => setFilters({
                    account: '',
                    from: '',
                    to: '',
                    subject: '',
                    q: '',
                    has_attachments: '',
                    date_from: '',
                    date_to: '',
                  })}
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Clear Filters
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Email Count */}
        <div className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          {totalCount > 0 && `${totalCount} ${totalCount === 1 ? 'email' : 'emails'}`}
          {totalPages > 1 && ` (Page ${currentPage} of ${totalPages})`}
        </div>

        {/* Email List */}
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-2 text-gray-600 dark:text-gray-400">Loading emails...</p>
          </div>
        ) : emails.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            No emails found
          </div>
        ) : (
          <div className="space-y-2">
            {emails.map(email => (
              <div
                key={email.id}
                onClick={() => handleEmailClick(email)}
                className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 hover:shadow-md transition cursor-pointer"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">
                        {email.subject || '(No Subject)'}
                      </h3>
                      {email.has_attachments && (
                        <span className="text-gray-500" title={`${email.attachment_count} attachments`}>
                          📎
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 truncate">
                      From: {email.from_address}
                    </p>
                    {email.to_addresses && email.to_addresses.length > 0 && (
                      <p className="text-sm text-gray-500 dark:text-gray-500 truncate">
                        To: {email.to_addresses.join(', ')}
                      </p>
                    )}
                  </div>
                  <div className="text-right text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
                    {formatDate(email.date)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-center gap-2">
            <button
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
              className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              ««
            </button>
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              ‹ Prev
            </button>
            <span className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              Next ›
            </button>
            <button
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
              className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              »»
            </button>
          </div>
        )}

      {/* Email Detail Modal */}
      {selectedEmail && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                  {selectedEmail.subject || '(No Subject)'}
                </h2>
                <div className="space-y-1 text-sm">
                  <p className="text-gray-700 dark:text-gray-300">
                    <span className="font-medium">From:</span> {selectedEmail.from_address}
                  </p>
                  {selectedEmail.to_addresses && selectedEmail.to_addresses.length > 0 && (
                    <p className="text-gray-700 dark:text-gray-300">
                      <span className="font-medium">To:</span> {selectedEmail.to_addresses.join(', ')}
                    </p>
                  )}
                  {selectedEmail.cc_addresses && selectedEmail.cc_addresses.length > 0 && (
                    <p className="text-gray-700 dark:text-gray-300">
                      <span className="font-medium">Cc:</span> {selectedEmail.cc_addresses.join(', ')}
                    </p>
                  )}
                  <p className="text-gray-600 dark:text-gray-400">
                    <span className="font-medium">Date:</span> {formatDate(selectedEmail.date)}
                  </p>
                  {selectedEmail.has_attachments && (
                    <p className="text-gray-600 dark:text-gray-400">
                      📎 {selectedEmail.attachment_count} {selectedEmail.attachment_count === 1 ? 'attachment' : 'attachments'}
                    </p>
                  )}
                </div>
              </div>
              <button
                onClick={() => setSelectedEmail(null)}
                className="ml-4 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            {/* Body */}
            <div className="flex-1 overflow-y-auto p-4">
              {selectedEmail.body_html ? (
                <div 
                  className="prose dark:prose-invert max-w-none"
                  dangerouslySetInnerHTML={{ __html: selectedEmail.body_html }}
                />
              ) : selectedEmail.body_text ? (
                <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 font-sans">
                  {selectedEmail.body_text}
                </pre>
              ) : (
                <p className="text-gray-500 dark:text-gray-400 italic">No content</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default EmailViewer;
