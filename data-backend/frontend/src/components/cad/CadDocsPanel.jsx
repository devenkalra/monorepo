import React, { useState, useEffect } from 'react';
import { marked } from 'marked';

export default function CadDocsPanel({ documentation }) {
  const [html, setHtml] = useState('');
  const text = documentation && String(documentation).trim();

  useEffect(() => {
    if (!text) {
      setHtml('');
      return;
    }
    (async () => {
      try {
        const result = await marked.parse(text);
        setHtml(result || '');
      } catch {
        setHtml('');
      }
    })();
  }, [text]);

  if (!text) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No documentation available. Add DOCUMENTATION to your model script.
      </p>
    );
  }

  if (!html) return <pre className="text-sm whitespace-pre-wrap text-gray-400">{text}</pre>;

  return (
    <div
      className="cad-docs-markdown text-sm text-gray-400 dark:text-gray-300 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h1]:text-gray-100 [&_h2]:text-gray-100 [&_h3]:text-gray-100 [&_p]:my-1 [&_code]:bg-gray-800 [&_code]:px-1 [&_code]:rounded [&_pre]:bg-gray-900 [&_pre]:p-3 [&_pre]:overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
