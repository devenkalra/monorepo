import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function ProfileEdit() {
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();
  const [displayname, setDisplayname] = useState(user?.displayname ?? user?.username ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await updateUser({ displayname: displayname.trim() || null });
      navigate(-1);
    } catch (err) {
      setError(err.message || 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  if (!user) return null;

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-[#0d1117] text-gray-900 dark:text-[#e6edf3]">
      <div className="max-w-md mx-auto p-6">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-blue-600 dark:text-[#58a6ff] hover:underline mb-4"
        >
          ← Back
        </button>
        <h1 className="text-xl font-bold text-gray-900 dark:text-[#e6edf3] mb-4">Edit Profile</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-[#8b949e] mb-1">Display name</label>
            <input
              type="text"
              value={displayname}
              onChange={(e) => setDisplayname(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-[#30363d] bg-white dark:bg-[#161b22] text-gray-900 dark:text-[#e6edf3]"
              placeholder="Enter display name (any characters)"
            />
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-[#8b949e]">Email: {user.email}</p>
            <p className="text-xs text-gray-500 dark:text-[#8b949e] mt-1">Email cannot be changed here.</p>
          </div>
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 dark:bg-[#58a6ff] text-white rounded-lg hover:bg-blue-700 dark:hover:bg-[#79b8ff] disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="px-4 py-2 bg-gray-200 dark:bg-[#21262d] text-gray-800 dark:text-[#e6edf3] rounded-lg hover:bg-gray-300 dark:hover:bg-[#30363d]"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
