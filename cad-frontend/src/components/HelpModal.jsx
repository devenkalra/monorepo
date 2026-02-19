import React from 'react';

const CAD_HELP = (
  <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
    <p><strong>3D CAD</strong> — Parameterized 3D modeling for woodworking, 3D printing, and more.</p>
    <ul className="list-disc list-inside space-y-1 ml-2">
      <li><strong>Models</strong> — Create models with Python scripts using cadlib (ThBody, ThAssembly).</li>
      <li><strong>Parameters</strong> — Define a PARAMETERS dict; adjust values to change dimensions in real time.</li>
      <li><strong>Documentation</strong> — View docstrings and parameter docs from your script.</li>
      <li><strong>Export</strong> — Download STL for CNC or 3D printing.</li>
    </ul>
  </div>
);

export default function HelpModal({ open, onClose }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-[#161b22] rounded-lg shadow-xl max-w-md w-full mx-4 p-6 border border-gray-200 dark:border-[#30363d]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-[#e6edf3]">Help — CAD</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:hover:text-[#8b949e] text-2xl leading-none"
          >
            ×
          </button>
        </div>
        {CAD_HELP}
      </div>
    </div>
  );
}
