import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';

export default function ProgressModal({ taskId, taskType, onComplete, onCancel, apiEndpoint = '/api/entities' }) {
  const [progress, setProgress] = useState({
    current: 0,
    total: 0,
    percentage: 0,
    status: 'processing',
    message: '',
    errors: []
  });
  const [cancelling, setCancelling] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const pollIntervalRef = useRef(null);

  useEffect(() => {
    if (!taskId) return;

    // Poll for progress updates
    const pollProgress = async () => {
      try {
        const response = await api.fetch(`${apiEndpoint}/task_progress/?task_id=${taskId}`);
        const data = await response.json();
        
        setProgress(data);

        // Stop polling if task is complete, failed, or cancelled
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          
          // Don't auto-close - wait for user to click OK
          // onComplete will be called when user clicks the OK button
        }
      } catch (error) {
        console.error('Failed to fetch progress:', error);
      }
    };

    // Initial poll
    pollProgress();

    // Poll every 500ms for more responsive progress updates
    pollIntervalRef.current = setInterval(pollProgress, 500);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [taskId, onComplete]);

  const handleCancelClick = () => {
    setShowCancelConfirm(true);
  };

  const handleCancelConfirm = async () => {
    setShowCancelConfirm(false);
    setCancelling(true);
    
    try {
      await api.fetch(`${apiEndpoint}/cancel_task/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId })
      });
    } catch (error) {
      console.error('Failed to cancel task:', error);
      setCancelling(false);
    }
  };

  const handleCancelDeny = () => {
    setShowCancelConfirm(false);
  };
  
  const handleClose = () => {
    // Only allow closing if task is complete, failed, or cancelled
    if (['completed', 'failed', 'cancelled'].includes(progress.status)) {
      onCancel();
    }
  };

  const getStatusColor = () => {
    switch (progress.status) {
      case 'completed': return 'text-green-600';
      case 'failed': return 'text-red-600';
      case 'cancelled': return 'text-yellow-600';
      default: return 'text-blue-600';
    }
  };

  const getStatusIcon = () => {
    switch (progress.status) {
      case 'completed':
        return (
          <svg className="w-12 h-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        );
      case 'failed':
        return (
          <svg className="w-12 h-12 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        );
      case 'cancelled':
        return (
          <svg className="w-12 h-12 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        );
      default:
        return (
          <svg className="w-12 h-12 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        );
    }
  };

  return (
    <>
      {/* Main Progress Modal */}
      <div 
        className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
        onClick={(e) => {
          // Prevent closing by clicking outside during processing
          if (progress.status === 'processing') {
            e.stopPropagation();
          }
        }}
      >
        <div 
          className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 max-w-md w-full mx-4"
          onClick={(e) => e.stopPropagation()}
        >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {taskType === 'import' && 'Importing Data'}
            {taskType === 'export' && 'Exporting Data'}
            {taskType === 'reindex' && 'Reindexing Search'}
            {taskType === 'email-import' && 'Importing Emails'}
          </h3>
        </div>

        {/* Status Icon */}
        <div className="flex justify-center mb-4">
          {getStatusIcon()}
        </div>

        {/* Progress Bar */}
        {progress.total > 0 && (
          <div className="mb-4">
            <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400 mb-1">
              <span>{progress.current} / {progress.total}</span>
              <span>{progress.percentage}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${
                  progress.status === 'completed' ? 'bg-green-500' :
                  progress.status === 'failed' ? 'bg-red-500' :
                  progress.status === 'cancelled' ? 'bg-yellow-500' :
                  'bg-blue-500'
                }`}
                style={{ width: `${progress.percentage}%` }}
              />
            </div>
          </div>
        )}

        {/* Status Message */}
        <div className={`text-center mb-4 ${getStatusColor()}`}>
          <p className="font-medium">{progress.message || 'Processing...'}</p>
          {cancelling && progress.status === 'processing' && (
            <p className="text-sm text-gray-500 mt-1">Cancelling...</p>
          )}
        </div>

        {/* Errors */}
        {progress.errors && progress.errors.length > 0 && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-3 mb-4">
            <p className="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
              Errors ({progress.errors.length}):
            </p>
            <div className="text-xs text-red-700 dark:text-red-300 max-h-32 overflow-y-auto">
              {progress.errors.slice(0, 5).map((error, i) => (
                <div key={i} className="mb-1">• {error}</div>
              ))}
              {progress.errors.length > 5 && (
                <div className="text-red-600 dark:text-red-400 mt-1">
                  ... and {progress.errors.length - 5} more
                </div>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-2">
          {/* Cancel Button (only show during processing) */}
          {progress.status === 'processing' && !cancelling && (
            <button
              onClick={handleCancelClick}
              className="flex-1 bg-red-500 hover:bg-red-600 text-white font-medium py-2 px-4 rounded transition-colors flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancel
            </button>
          )}
          
          {/* Cancelling indicator */}
          {cancelling && progress.status === 'processing' && (
            <button
              disabled
              className="flex-1 bg-gray-400 text-white font-medium py-2 px-4 rounded cursor-not-allowed"
            >
              Cancelling...
            </button>
          )}
          
          {/* OK Button (only show when complete/failed/cancelled) */}
          {['completed', 'failed', 'cancelled'].includes(progress.status) && (
            <button
              onClick={() => {
                handleClose();
                onComplete(progress);
              }}
              className="flex-1 bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded transition-colors"
            >
              OK
            </button>
          )}
        </div>
      </div>
    </div>

      {/* Cancel Confirmation Modal */}
      {showCancelConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl p-6 max-w-sm w-full mx-4">
            {/* Warning Icon */}
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
                <svg className="w-10 h-10 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
            </div>

            {/* Title */}
            <h3 className="text-xl font-bold text-gray-900 dark:text-white text-center mb-3">
              Cancel Task?
            </h3>

            {/* Message */}
            <p className="text-gray-600 dark:text-gray-300 text-center mb-6">
              Are you sure you want to cancel this task? All progress will be lost and changes will be rolled back.
            </p>

            {/* Buttons */}
            <div className="flex gap-3">
              <button
                onClick={handleCancelDeny}
                className="flex-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 font-medium py-2 px-4 rounded transition-colors"
              >
                No, Continue
              </button>
              <button
                onClick={handleCancelConfirm}
                className="flex-1 bg-red-500 hover:bg-red-600 text-white font-medium py-2 px-4 rounded transition-colors"
              >
                Yes, Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
