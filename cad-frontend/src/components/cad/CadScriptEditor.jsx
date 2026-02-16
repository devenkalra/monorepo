import React from 'react';

export default function CadScriptEditor({ value, onChange, readOnly }) {
  return (
    <textarea
      value={value || ''}
      onChange={(e) => onChange?.(e.target.value)}
      readOnly={readOnly}
      spellCheck={false}
      className="w-full h-full min-h-[120px] p-3 text-sm font-mono bg-gray-200 dark:bg-[#21262d] text-gray-900 dark:text-[#e6edf3] border-0 resize-none focus:outline-none focus:ring-0"
      style={{ fontFamily: 'JetBrains Mono, Fira Code, Monaco, monospace' }}
      placeholder="Select a model or create a new one..."
    />
  );
}
