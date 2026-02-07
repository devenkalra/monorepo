import React, { useState } from 'react';

// Placeholder tag tree – in real app fetch from API
const TAG_TREE = [
    'Person',
    'Note',
    'Education',
    'Location',
    'Company',
    'Project',
    'Event',
];

// Placeholder entity types
const ENTITY_TYPES = ['Person', 'Note', 'Organization', 'Location', 'Event'];

// Placeholder relation types
const RELATION_TYPES = [
    'IS_CHILD_OF',
    'IS_PARENT_OF',
    'IS_SPOUSE_OF',
    'WORKS_AT',
    'STUDIED_AT',
    'LOCATED_IN',
];

function SearchBar({ query, setQuery, filters, setFilters }) {
    const [showTagTree, setShowTagTree] = useState(false);
    const [activePanel, setActivePanel] = useState(null); // 'tags' | 'types' | 'display' | 'relations'
    
    // Local state for relation panel
    const [relationEntity, setRelationEntity] = useState('');
    const [relationEntitySuggestions, setRelationEntitySuggestions] = useState([]);
    const [selectedRelationEntity, setSelectedRelationEntity] = useState(null);
    const [selectedRelationType, setSelectedRelationType] = useState('');

    const handleQueryChange = (e) => {
        setQuery(e.target.value);
    };

    const handleTagTreeClick = (tag) => {
        // Set primary tag and close tree
        setFilters({ ...filters, primaryTag: tag });
        setShowTagTree(false);
    };

    const toggleTag = (tag) => {
        const currentTags = filters.tags || [];
        if (currentTags.includes(tag)) {
            setFilters({ ...filters, tags: currentTags.filter(t => t !== tag) });
        } else {
            setFilters({ ...filters, tags: [...currentTags, tag] });
        }
    };

    const toggleType = (type) => {
        const currentTypes = filters.types || [];
        if (currentTypes.includes(type)) {
            setFilters({ ...filters, types: currentTypes.filter(t => t !== type) });
        } else {
            setFilters({ ...filters, types: [...currentTypes, type] });
        }
    };

    const handleDisplayApply = (displayText) => {
        setFilters({ ...filters, display: displayText });
        setActivePanel(null);
    };

    const handleRelationEntitySearch = async (searchText) => {
        setRelationEntity(searchText);
        if (!searchText.trim()) {
            setRelationEntitySuggestions([]);
            return;
        }
        
        // Fetch matching entities from API using api client
        try {
            const { default: api } = await import('../services/api');
            const data = await api.search(searchText, { limit: 5 });
            setRelationEntitySuggestions(Array.isArray(data) ? data : []);
        } catch (error) {
            console.error('Failed to fetch entity suggestions', error);
            setRelationEntitySuggestions([]);
        }
    };

    const handleRelationApply = () => {
        if (selectedRelationEntity && selectedRelationType) {
            setFilters({
                ...filters,
                relation: {
                    entity: selectedRelationEntity,
                    type: selectedRelationType,
                },
            });
            setActivePanel(null);
            // Reset relation panel state
            setRelationEntity('');
            setSelectedRelationEntity(null);
            setSelectedRelationType('');
            setRelationEntitySuggestions([]);
        }
    };

    const handleRelationClear = () => {
        setFilters({ ...filters, relation: null });
        setRelationEntity('');
        setSelectedRelationEntity(null);
        setSelectedRelationType('');
        setRelationEntitySuggestions([]);
    };

    const removePrimaryTag = () => {
        setFilters({ ...filters, primaryTag: '' });
    };

    const removeTag = (tag) => {
        setFilters({ ...filters, tags: (filters.tags || []).filter(t => t !== tag) });
    };

    const removeType = (type) => {
        setFilters({ ...filters, types: (filters.types || []).filter(t => t !== type) });
    };

    const removeDisplay = () => {
        setFilters({ ...filters, display: '' });
    };

    const removeRelation = () => {
        setFilters({ ...filters, relation: null });
    };

    return (
        <div className="mb-4 relative">
            {/* Search input */}
            <div className="flex items-center bg-white dark:bg-gray-800 rounded-xl shadow px-3 py-2">
                <button
                    className="mr-2 rounded-full p-2 hover:bg-gray-100 dark:hover:bg-gray-700"
                    onClick={() => setShowTagTree(true)}
                    aria-label="Open tag tree"
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-5 w-5 text-gray-600 dark:text-gray-300"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h8m-8 6h16" />
                    </svg>
                </button>
                <input
                    type="text"
                    placeholder="Search entities..."
                    value={query}
                    onChange={handleQueryChange}
                    className="flex-1 bg-transparent outline-none text-gray-900 dark:text-gray-100"
                />
            </div>

            {/* Filter buttons */}
            <div className="flex gap-2 mt-3 flex-wrap">
                <button
                    onClick={() => setActivePanel(activePanel === 'tags' ? null : 'tags')}
                    className="px-3 py-1.5 rounded-lg bg-blue-500 text-white hover:bg-blue-600 text-sm font-medium"
                >
                    Tags
                </button>
                <button
                    onClick={() => setActivePanel(activePanel === 'types' ? null : 'types')}
                    className="px-3 py-1.5 rounded-lg bg-green-500 text-white hover:bg-green-600 text-sm font-medium"
                >
                    Type
                </button>
                <button
                    onClick={() => setActivePanel(activePanel === 'display' ? null : 'display')}
                    className="px-3 py-1.5 rounded-lg bg-purple-500 text-white hover:bg-purple-600 text-sm font-medium"
                >
                    Display
                </button>
                <button
                    onClick={() => setActivePanel(activePanel === 'relations' ? null : 'relations')}
                    className="px-3 py-1.5 rounded-lg bg-orange-500 text-white hover:bg-orange-600 text-sm font-medium"
                >
                    Relations
                </button>
            </div>

            {/* Active filter chips */}
            {(filters.primaryTag || (filters.tags && filters.tags.length > 0) || (filters.types && filters.types.length > 0) || filters.display || filters.relation) && (
                <div className="flex gap-2 mt-3 flex-wrap">
                    {filters.primaryTag && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 text-sm">
                            Primary: {filters.primaryTag}
                            <button onClick={removePrimaryTag} className="hover:text-blue-600">✕</button>
                        </span>
                    )}
                    {filters.tags && filters.tags.map((tag) => (
                        <span key={tag} className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 text-sm">
                            Tag: {tag}
                            <button onClick={() => removeTag(tag)} className="hover:text-blue-600">✕</button>
                        </span>
                    ))}
                    {filters.types && filters.types.map((type) => (
                        <span key={type} className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 text-sm">
                            Type: {type}
                            <button onClick={() => removeType(type)} className="hover:text-green-600">✕</button>
                        </span>
                    ))}
                    {filters.display && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 text-sm">
                            Display: {filters.display}
                            <button onClick={removeDisplay} className="hover:text-purple-600">✕</button>
                        </span>
                    )}
                    {filters.relation && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200 text-sm">
                            {filters.relation.type} {filters.relation.entity.display || filters.relation.entity.label}
                            <button onClick={removeRelation} className="hover:text-orange-600">✕</button>
                        </span>
                    )}
                </div>
            )}

            {/* Tag Tree - slides in from left */}
            {showTagTree && (
                <>
                    <div
                        className="fixed inset-0 bg-black bg-opacity-30 z-40"
                        onClick={() => setShowTagTree(false)}
                    />
                    <div className="fixed left-0 top-0 bottom-0 w-64 bg-white dark:bg-gray-800 shadow-lg z-50 p-4 overflow-y-auto">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold">Select Primary Tag</h3>
                            <button onClick={() => setShowTagTree(false)} className="text-gray-600 dark:text-gray-300">✕</button>
                        </div>
                        <ul className="space-y-2">
                            {TAG_TREE.map((tag) => (
                                <li key={tag}>
                                    <button
                                        onClick={() => handleTagTreeClick(tag)}
                                        className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                                    >
                                        {tag}
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>
                </>
            )}

            {/* Tags Panel - slides in from bottom */}
            {activePanel === 'tags' && (
                <>
                    <div
                        className="fixed inset-0 bg-black bg-opacity-30 z-40"
                        onClick={() => setActivePanel(null)}
                    />
                    <div className="fixed left-0 right-0 bottom-0 bg-white dark:bg-gray-800 shadow-lg z-50 p-4 rounded-t-2xl max-h-96 overflow-y-auto">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold">Select Tags (OR)</h3>
                            <button onClick={() => setActivePanel(null)} className="text-gray-600 dark:text-gray-300">✕</button>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {TAG_TREE.map((tag) => (
                                <button
                                    key={tag}
                                    onClick={() => toggleTag(tag)}
                                    className={`px-3 py-2 rounded-lg ${
                                        (filters.tags || []).includes(tag)
                                            ? 'bg-blue-600 text-white'
                                            : 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                                    }`}
                                >
                                    {tag}
                                </button>
                            ))}
                        </div>
                    </div>
                </>
            )}

            {/* Types Panel - slides in from bottom */}
            {activePanel === 'types' && (
                <>
                    <div
                        className="fixed inset-0 bg-black bg-opacity-30 z-40"
                        onClick={() => setActivePanel(null)}
                    />
                    <div className="fixed left-0 right-0 bottom-0 bg-white dark:bg-gray-800 shadow-lg z-50 p-4 rounded-t-2xl max-h-96 overflow-y-auto">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold">Select Types</h3>
                            <button onClick={() => setActivePanel(null)} className="text-gray-600 dark:text-gray-300">✕</button>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {ENTITY_TYPES.map((type) => (
                                <button
                                    key={type}
                                    onClick={() => toggleType(type)}
                                    className={`px-3 py-2 rounded-lg ${
                                        (filters.types || []).includes(type)
                                            ? 'bg-green-600 text-white'
                                            : 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                                    }`}
                                >
                                    {type}
                                </button>
                            ))}
                        </div>
                    </div>
                </>
            )}

            {/* Display Panel - slides in from bottom */}
            {activePanel === 'display' && (
                <>
                    <div
                        className="fixed inset-0 bg-black bg-opacity-30 z-40"
                        onClick={() => setActivePanel(null)}
                    />
                    <div className="fixed left-0 right-0 bottom-0 bg-white dark:bg-gray-800 shadow-lg z-50 p-4 rounded-t-2xl">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold">Search Display</h3>
                            <button onClick={() => setActivePanel(null)} className="text-gray-600 dark:text-gray-300">✕</button>
                        </div>
                        <input
                            type="text"
                            placeholder="Type display text..."
                            value={filters.display || ''}
                            onChange={(e) => handleDisplayApply(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                            autoFocus
                        />
                    </div>
                </>
            )}

            {/* Relations Panel - slides in from bottom */}
            {activePanel === 'relations' && (
                <>
                    <div
                        className="fixed inset-0 bg-black bg-opacity-30 z-40"
                        onClick={() => setActivePanel(null)}
                    />
                    <div className="fixed left-0 right-0 bottom-0 bg-white dark:bg-gray-800 shadow-lg z-50 p-4 rounded-t-2xl max-h-96 overflow-y-auto">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold">Search by Relation</h3>
                            <button onClick={() => setActivePanel(null)} className="text-gray-600 dark:text-gray-300">✕</button>
                        </div>
                        
                        {/* Entity search */}
                        <div className="mb-4">
                            <label className="block text-sm font-medium mb-2">Entity Display Name</label>
                            <input
                                type="text"
                                placeholder="Type to search entities..."
                                value={relationEntity}
                                onChange={(e) => handleRelationEntitySearch(e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                            />
                            {relationEntitySuggestions.length > 0 && (
                                <ul className="mt-2 border border-gray-300 dark:border-gray-600 rounded-lg max-h-40 overflow-y-auto">
                                    {relationEntitySuggestions.map((entity) => (
                                        <li
                                            key={entity.id}
                                            onClick={() => {
                                                setSelectedRelationEntity(entity);
                                                setRelationEntity(entity.display || entity.label);
                                                setRelationEntitySuggestions([]);
                                            }}
                                            className="px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer"
                                        >
                                            {entity.display || entity.label} <span className="text-xs text-gray-500">({entity.type})</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>

                        {/* Relation type dropdown */}
                        {selectedRelationEntity && (
                            <div className="mb-4">
                                <label className="block text-sm font-medium mb-2">Relation Type</label>
                                <select
                                    value={selectedRelationType}
                                    onChange={(e) => setSelectedRelationType(e.target.value)}
                                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                >
                                    <option value="">Select relation...</option>
                                    {RELATION_TYPES.map((relType) => (
                                        <option key={relType} value={relType}>
                                            {relType}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}

                        {/* Action buttons */}
                        <div className="flex gap-2">
                            <button
                                onClick={handleRelationApply}
                                disabled={!selectedRelationEntity || !selectedRelationType}
                                className="flex-1 px-4 py-2 rounded-lg bg-orange-500 text-white hover:bg-orange-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
                            >
                                Apply
                            </button>
                            <button
                                onClick={handleRelationClear}
                                className="px-4 py-2 rounded-lg bg-gray-300 dark:bg-gray-600 text-gray-900 dark:text-gray-100 hover:bg-gray-400 dark:hover:bg-gray-500"
                            >
                                Clear
                            </button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

export default SearchBar;
