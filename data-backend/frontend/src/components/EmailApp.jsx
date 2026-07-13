import React, { useState } from 'react';
import EmailViewer from './EmailViewer';
import EmailImporter from './EmailImporter';

function EmailApp() {
  const [activeTab, setActiveTab] = useState('viewer');

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      <div className="mx-auto max-w-7xl p-4">
        {/* Tab Navigation */}
        <div className="mb-6 border-b border-gray-200 dark:border-gray-700">
          <nav className="flex gap-8">
            <button
              onClick={() => setActiveTab('viewer')}
              className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'viewer'
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              📧 Email Viewer
            </button>
            <button
              onClick={() => setActiveTab('importer')}
              className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'importer'
                  ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              ⚙️ Import Manager
            </button>
          </nav>
        </div>

        {/* Tab Content */}
        {activeTab === 'viewer' ? <EmailViewer /> : <EmailImporter />}
      </div>
    </div>
  );
}

export default EmailApp;
