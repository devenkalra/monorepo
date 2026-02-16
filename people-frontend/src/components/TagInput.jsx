import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';

function TagInput({ value = [], onChange, disabled = false }) {
    const [inputValue, setInputValue] = useState('');
    const [suggestions, setSuggestions] = useState([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const inputRef = useRef(null);
    const suggestionsRef = useRef(null);

    // Fetch tag suggestions based on input
    useEffect(() => {
        if (!inputValue.trim()) {
            setSuggestions([]);
            return;
        }

        const fetchSuggestions = async () => {
            try {
                const resp = await api.fetch(`/api/tags/?limit=100`);
                const data = await resp.json();
                const tagList = data.results || data;
                
                // Filter tags that contain the input substring
                const filtered = tagList
                    .filter(tag => tag.name.toLowerCase().includes(inputValue.toLowerCase()))
                    .slice(0, 10);
                
                setSuggestions(filtered);
            } catch (error) {
                console.error('Failed to fetch tag suggestions:', error);
                setSuggestions([]);
            }
        };

        const timeout = setTimeout(fetchSuggestions, 200);
        return () => clearTimeout(timeout);
    }, [inputValue]);

    // Close suggestions when clicking outside
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (
                suggestionsRef.current &&
                !suggestionsRef.current.contains(event.target) &&
                !inputRef.current.contains(event.target)
            ) {
                setShowSuggestions(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const addTag = (tagName) => {
        if (!value.includes(tagName)) {
            onChange([...value, tagName]);
        }
        setInputValue('');
        setSuggestions([]);
        setShowSuggestions(false);
    };

    const removeTag = (tagToRemove) => {
        onChange(value.filter(tag => tag !== tagToRemove));
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (inputValue.trim()) {
                // Create new tag
                addTag(inputValue.trim());
            }
        }
    };

    return (
        <div className="space-y-2">
            {/* Selected Tags */}
            {value.length > 0 && (
                <div className="flex flex-wrap gap-2">
                    {value.map((tag, idx) => (
                        <span
                            key={idx}
                            className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-sm"
                        >
                            {tag}
                            {!disabled && (
                                <button
                                    type="button"
                                    onClick={() => removeTag(tag)}
                                    className="hover:text-blue-600 dark:hover:text-blue-400"
                                >
                                    ×
                                </button>
                            )}
                        </span>
                    ))}
                </div>
            )}

            {/* Input Field */}
            {!disabled && (
                <div className="relative">
                    <input
                        ref={inputRef}
                        type="text"
                        value={inputValue}
                        onChange={(e) => {
                            setInputValue(e.target.value);
                            setShowSuggestions(true);
                        }}
                        onFocus={() => setShowSuggestions(true)}
                        onKeyDown={handleKeyDown}
                        placeholder="Type to search tags or create new..."
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
                    />

                    {/* Suggestions Dropdown */}
                    {showSuggestions && (inputValue.trim() || suggestions.length > 0) && (
                        <div
                            ref={suggestionsRef}
                            className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg shadow-lg max-h-60 overflow-y-auto"
                        >
                            {suggestions.length > 0 ? (
                                <>
                                    {suggestions.map((tag) => (
                                        <button
                                            key={tag.name}
                                            type="button"
                                            onClick={() => addTag(tag.name)}
                                            className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-between"
                                        >
                                            <span className="text-gray-900 dark:text-gray-100">{tag.name}</span>
                                            <span className="text-xs text-gray-500 dark:text-gray-400">
                                                ({tag.count})
                                            </span>
                                        </button>
                                    ))}
                                    {inputValue.trim() && !suggestions.find(t => t.name === inputValue.trim()) && (
                                        <button
                                            type="button"
                                            onClick={() => addTag(inputValue.trim())}
                                            className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 border-t border-gray-200 dark:border-gray-700 text-blue-600 dark:text-blue-400 font-medium"
                                        >
                                            + Create new tag "{inputValue.trim()}"
                                        </button>
                                    )}
                                </>
                            ) : inputValue.trim() ? (
                                <button
                                    type="button"
                                    onClick={() => addTag(inputValue.trim())}
                                    className="w-full text-left px-4 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 text-blue-600 dark:text-blue-400 font-medium"
                                >
                                    + Create new tag "{inputValue.trim()}"
                                </button>
                            ) : null}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default TagInput;
