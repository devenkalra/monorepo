import React, { useState, useEffect } from 'react';
import api from '../services/api';
import ProgressModal from './ProgressModal';

function EmailImporter() {
  const [accounts, setAccounts] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [showAccountForm, setShowAccountForm] = useState(false);
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [editingConfig, setEditingConfig] = useState(null);
  const [progressTask, setProgressTask] = useState(null);
  
  const [accountForm, setAccountForm] = useState({
    name: '',
    email_address: '',
    imap_host: 'imap.gmail.com',
    imap_port: 993,
    imap_use_ssl: true,
    username: '',
    password: '',
    is_active: true,
  });
  
  const [configForm, setConfigForm] = useState({
    account: '',
    name: '',
    mailbox: 'INBOX',
    from_filter: '',
    to_filter: '',
    subject_filter: '',
    labels: [],
    since_date: '',
    max_emails: 100,
    is_active: true,
  });

  useEffect(() => {
    fetchAccounts();
    fetchConfigs();
  }, []);

  const fetchAccounts = async () => {
    try {
      const resp = await api.fetch('/api/mail/accounts/');
      const data = await resp.json();
      setAccounts(data || []);
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
    }
  };

  const fetchConfigs = async () => {
    try {
      const resp = await api.fetch('/api/mail/configs/');
      const data = await resp.json();
      setConfigs(data || []);
    } catch (error) {
      console.error('Failed to fetch configs:', error);
    }
  };

  const handleSaveAccount = async (e) => {
    e.preventDefault();
    
    try {
      const url = editingAccount 
        ? `/api/mail/accounts/${editingAccount.id}/`
        : '/api/mail/accounts/';
      const method = editingAccount ? 'PUT' : 'POST';
      
      const resp = await api.fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(accountForm),
      });
      
      if (!resp.ok) throw new Error('Failed to save account');
      
      await fetchAccounts();
      setShowAccountForm(false);
      setEditingAccount(null);
      resetAccountForm();
    } catch (error) {
      console.error('Error saving account:', error);
      alert('Failed to save account. Please try again.');
    }
  };

  const handleSaveConfig = async (e) => {
    e.preventDefault();
    
    try {
      const url = editingConfig 
        ? `/api/mail/configs/${editingConfig.id}/`
        : '/api/mail/configs/';
      const method = editingConfig ? 'PUT' : 'POST';
      
      const resp = await api.fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configForm),
      });
      
      if (!resp.ok) throw new Error('Failed to save config');
      
      await fetchConfigs();
      setShowConfigForm(false);
      setEditingConfig(null);
      resetConfigForm();
    } catch (error) {
      console.error('Error saving config:', error);
      alert('Failed to save configuration. Please try again.');
    }
  };

  const handleTestConnection = async (accountId) => {
    try {
      const resp = await api.fetch(`/api/mail/accounts/${accountId}/test_connection/`, {
        method: 'POST',
      });
      const data = await resp.json();
      
      if (data.success) {
        alert(`Connection successful!\n\nFound ${data.mailboxes?.length || 0} mailboxes.`);
      } else {
        alert(`Connection failed: ${data.error}`);
      }
    } catch (error) {
      console.error('Connection test error:', error);
      alert('Connection test failed. Please check your credentials.');
    }
  };

  const handleImportNow = async (configId) => {
    try {
      const resp = await api.fetch(`/api/mail/configs/${configId}/import_now/`, {
        method: 'POST',
      });
      const data = await resp.json();
      
      if (data.success && data.task_id) {
        setProgressTask({ taskId: data.task_id, taskType: 'email-import' });
      } else {
        alert(`Import failed: ${data.error}`);
      }
    } catch (error) {
      console.error('Import error:', error);
      alert('Failed to start import. Please try again.');
    }
  };

  const handleDeleteAccount = async (accountId) => {
    if (!confirm('Delete this email account? All associated emails will be deleted.')) {
      return;
    }
    
    try {
      await api.fetch(`/api/mail/accounts/${accountId}/`, { method: 'DELETE' });
      await fetchAccounts();
      await fetchConfigs();
    } catch (error) {
      console.error('Error deleting account:', error);
      alert('Failed to delete account.');
    }
  };

  const handleDeleteConfig = async (configId) => {
    if (!confirm('Delete this import configuration?')) {
      return;
    }
    
    try {
      await api.fetch(`/api/mail/configs/${configId}/`, { method: 'DELETE' });
      await fetchConfigs();
    } catch (error) {
      console.error('Error deleting config:', error);
      alert('Failed to delete configuration.');
    }
  };

  const resetAccountForm = () => {
    setAccountForm({
      name: '',
      email_address: '',
      imap_host: 'imap.gmail.com',
      imap_port: 993,
      imap_use_ssl: true,
      username: '',
      password: '',
      is_active: true,
    });
  };

  const resetConfigForm = () => {
    setConfigForm({
      account: '',
      name: '',
      mailbox: 'INBOX',
      from_filter: '',
      to_filter: '',
      subject_filter: '',
      labels: [],
      since_date: '',
      max_emails: 100,
      is_active: true,
    });
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      <div className="mx-auto max-w-6xl p-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Email Import Manager</h1>

        {/* Email Accounts Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Email Accounts</h2>
            <button
              onClick={() => {
                resetAccountForm();
                setEditingAccount(null);
                setShowAccountForm(true);
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              + Add Account
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {accounts.map(account => (
              <div key={account.id} className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="font-medium text-gray-900 dark:text-gray-100">{account.name}</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{account.email_address}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                      {account.imap_host}:{account.imap_port}
                    </p>
                  </div>
                  <span className={`px-2 py-1 text-xs rounded ${account.is_active ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}>
                    {account.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                
                {account.last_sync && (
                  <p className="text-xs text-gray-500 dark:text-gray-500 mb-3">
                    Last sync: {new Date(account.last_sync).toLocaleString()}
                  </p>
                )}
                
                <div className="flex gap-2">
                  <button
                    onClick={() => handleTestConnection(account.id)}
                    className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                  >
                    Test
                  </button>
                  <button
                    onClick={() => {
                      setEditingAccount(account);
                      setAccountForm(account);
                      setShowAccountForm(true);
                    }}
                    className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteAccount(account.id)}
                    className="px-3 py-1 text-sm border border-red-300 dark:border-red-600 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Import Configurations Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Import Configurations</h2>
            <button
              onClick={() => {
                resetConfigForm();
                setEditingConfig(null);
                setShowConfigForm(true);
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              disabled={accounts.length === 0}
            >
              + Add Configuration
            </button>
          </div>

          {accounts.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">
              Add an email account first to create import configurations
            </p>
          ) : (
            <div className="space-y-3">
              {configs.map(config => (
                <div key={config.id} className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-medium text-gray-900 dark:text-gray-100">{config.name}</h3>
                        <span className={`px-2 py-1 text-xs rounded ${config.is_active ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}>
                          {config.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                        Account: {config.account_name} ({config.account_email})
                      </p>
                      <div className="text-xs text-gray-500 dark:text-gray-500 space-y-1">
                        <p>Mailbox: {config.mailbox}</p>
                        {config.from_filter && <p>From: {config.from_filter}</p>}
                        {config.to_filter && <p>To: {config.to_filter}</p>}
                        {config.subject_filter && <p>Subject: {config.subject_filter}</p>}
                        {config.since_date && <p>Since: {config.since_date}</p>}
                        <p>Max emails: {config.max_emails}</p>
                      </div>
                    </div>
                    
                    <div className="flex flex-col gap-2">
                      <button
                        onClick={() => handleImportNow(config.id)}
                        disabled={!config.is_active}
                        className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Import Now
                      </button>
                      <button
                        onClick={() => {
                          setEditingConfig(config);
                          setConfigForm(config);
                          setShowConfigForm(true);
                        }}
                        className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDeleteConfig(config.id)}
                        className="px-4 py-2 border border-red-300 dark:border-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Account Form Modal */}
        {showAccountForm && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  {editingAccount ? 'Edit Email Account' : 'Add Email Account'}
                </h2>
                
                <form onSubmit={handleSaveAccount} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Account Name
                    </label>
                    <input
                      type="text"
                      required
                      value={accountForm.name}
                      onChange={(e) => setAccountForm(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="My Gmail"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Email Address
                    </label>
                    <input
                      type="email"
                      required
                      value={accountForm.email_address}
                      onChange={(e) => setAccountForm(prev => ({ ...prev, email_address: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="user@gmail.com"
                    />
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        IMAP Host
                      </label>
                      <input
                        type="text"
                        required
                        value={accountForm.imap_host}
                        onChange={(e) => setAccountForm(prev => ({ ...prev, imap_host: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                        placeholder="imap.gmail.com"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        IMAP Port
                      </label>
                      <input
                        type="number"
                        required
                        value={accountForm.imap_port}
                        onChange={(e) => setAccountForm(prev => ({ ...prev, imap_port: parseInt(e.target.value) }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Username
                    </label>
                    <input
                      type="text"
                      required
                      value={accountForm.username}
                      onChange={(e) => setAccountForm(prev => ({ ...prev, username: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="Usually your email address"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Password / App Password
                    </label>
                    <input
                      type="password"
                      required
                      value={accountForm.password}
                      onChange={(e) => setAccountForm(prev => ({ ...prev, password: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="For Gmail, use App Password"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                      For Gmail: Enable 2FA and generate an App Password at myaccount.google.com/apppasswords
                    </p>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={accountForm.imap_use_ssl}
                      onChange={(e) => setAccountForm(prev => ({ ...prev, imap_use_ssl: e.target.checked }))}
                      className="rounded"
                    />
                    <label className="text-sm text-gray-700 dark:text-gray-300">Use SSL</label>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={accountForm.is_active}
                      onChange={(e) => setAccountForm(prev => ({ ...prev, is_active: e.target.checked }))}
                      className="rounded"
                    />
                    <label className="text-sm text-gray-700 dark:text-gray-300">Active</label>
                  </div>
                  
                  <div className="flex gap-3 pt-4">
                    <button
                      type="submit"
                      className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    >
                      Save Account
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowAccountForm(false);
                        setEditingAccount(null);
                        resetAccountForm();
                      }}
                      className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Config Form Modal */}
        {showConfigForm && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
                  {editingConfig ? 'Edit Import Configuration' : 'Add Import Configuration'}
                </h2>
                
                <form onSubmit={handleSaveConfig} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Configuration Name
                    </label>
                    <input
                      type="text"
                      required
                      value={configForm.name}
                      onChange={(e) => setConfigForm(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="Work Emails"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Email Account
                    </label>
                    <select
                      required
                      value={configForm.account}
                      onChange={(e) => setConfigForm(prev => ({ ...prev, account: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                    >
                      <option value="">Select account...</option>
                      {accounts.map(acc => (
                        <option key={acc.id} value={acc.id}>{acc.name} ({acc.email_address})</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Mailbox
                    </label>
                    <input
                      type="text"
                      required
                      value={configForm.mailbox}
                      onChange={(e) => setConfigForm(prev => ({ ...prev, mailbox: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="INBOX"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                      For Gmail: INBOX, [Gmail]/All Mail, [Gmail]/Sent Mail, etc.
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        From Filter (optional)
                      </label>
                      <input
                        type="text"
                        value={configForm.from_filter}
                        onChange={(e) => setConfigForm(prev => ({ ...prev, from_filter: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                        placeholder="sender@example.com"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        To Filter (optional)
                      </label>
                      <input
                        type="text"
                        value={configForm.to_filter}
                        onChange={(e) => setConfigForm(prev => ({ ...prev, to_filter: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                        placeholder="recipient@example.com"
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Subject Filter (optional)
                    </label>
                    <input
                      type="text"
                      value={configForm.subject_filter}
                      onChange={(e) => setConfigForm(prev => ({ ...prev, subject_filter: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      placeholder="Keywords in subject"
                    />
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Since Date (optional)
                      </label>
                      <input
                        type="date"
                        value={configForm.since_date}
                        onChange={(e) => setConfigForm(prev => ({ ...prev, since_date: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Max Emails per Import
                      </label>
                      <input
                        type="number"
                        required
                        min="1"
                        max="1000"
                        value={configForm.max_emails}
                        onChange={(e) => setConfigForm(prev => ({ ...prev, max_emails: parseInt(e.target.value) }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-transparent text-gray-900 dark:text-gray-100"
                      />
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={configForm.is_active}
                      onChange={(e) => setConfigForm(prev => ({ ...prev, is_active: e.target.checked }))}
                      className="rounded"
                    />
                    <label className="text-sm text-gray-700 dark:text-gray-300">Active</label>
                  </div>
                  
                  <div className="flex gap-3 pt-4">
                    <button
                      type="submit"
                      className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    >
                      Save Configuration
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowConfigForm(false);
                        setEditingConfig(null);
                        resetConfigForm();
                      }}
                      className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Progress Modal */}
        {progressTask && (
          <ProgressModal
            taskId={progressTask.taskId}
            taskType={progressTask.taskType}
            onComplete={() => {
              setProgressTask(null);
              // Refresh email list in viewer
            }}
            onCancel={() => {
              setProgressTask(null);
            }}
            apiEndpoint="/api/mail/emails"
          />
        )}
      </div>
    </div>
  );
}

export default EmailImporter;
