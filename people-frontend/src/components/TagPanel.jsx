import React from 'react';

function TagPanel({ visible, onClose, selectedTags, setSelectedTags }) {
    if (!visible) return null;
    // Placeholder tag list – in real app fetch from API
    const allTags = ['Person', 'Note', 'Education', 'Place'];
    const toggleTag = (tag) => {
        if (selectedTags.includes(tag)) {
            setSelectedTags(selectedTags.filter((t) => t !== tag));
        } else {
            setSelectedTags([...selectedTags, tag]);
        }
    };
    return (
        <div className="fixed inset-x-0 bottom-0 bg-white dark:bg-gray-800 p-4 shadow-lg transform transition-transform translate-y-0">
            <div className="flex justify-between items-center mb-2">
                <h2 className="text-lg font-medium">Select Tags (OR)</h2>
                <button onClick={onClose} className="text-gray-600 dark:text-gray-300">✕</button>
            </div>
            <div className="flex flex-wrap gap-2">
                {allTags.map((tag) => (
                    <button
                        key={tag}
                        onClick={() => toggleTag(tag)}
                        className={`px-2 py-1 rounded ${selectedTags.includes(tag) ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700'}`}
                    >
                        {tag}
                    </button>
                ))}
            </div>
        </div>
    );
}

export default TagPanel;
