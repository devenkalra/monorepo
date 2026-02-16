import React from 'react';

export default function CadParamsForm({ parameters, values, onChange }) {
  if (!parameters || Object.keys(parameters).length === 0) {
    return <p className="text-gray-500 dark:text-gray-400 text-sm">No parameters defined in this model.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {Object.entries(parameters).map(([key, defVal]) => {
        const val = values[key] ?? defVal;
        const type = typeof defVal === 'number' ? 'number' : 'text';
        return (
          <div key={key} className="flex flex-col gap-1">
            <label htmlFor={`param-${key}`} className="text-sm text-gray-500 dark:text-gray-400">
              {key}
            </label>
            <input
              type={type}
              id={`param-${key}`}
              data-param={key}
              value={val}
              step={type === 'number' ? '0.1' : undefined}
              onChange={(e) => {
                const v = type === 'number' ? parseFloat(e.target.value) : e.target.value;
                onChange({ ...values, [key]: v });
              }}
              className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-[#21262d] text-gray-900 dark:text-gray-100 text-sm"
            />
          </div>
        );
      })}
    </div>
  );
}
