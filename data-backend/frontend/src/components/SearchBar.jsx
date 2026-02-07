import React, { useState, useEffect, useMemo } from 'react';
import TagTreePanel from './TagTreePanel';
import api from '../services/api';

const ENTITY_TYPES = [
    'Person',
    'Note',
    'Organization',
    'Location',
    'Event',
    'Document',
];

const RELATION_TYPES = [
    'IS_CHILD_OF',
    'IS_PARENT_OF',
    'IS_SPOUSE_OF',
    'IS_FRIEND_OF',
    'IS_COLLEAGUE_OF',
    'IS_MANAGER_OF',
    'WORKS_FOR_MGR',
    'IS_STUDENT_OF',
    'IS_TEACHER_OF',
    'IS_RELATED_TO',
];

function SearchBar({ query, setQuery, filters, setFilters, sortBy, setSortBy, showSortMenu, setShowSortMenu }) {
    const [activePanel, setActivePanel] = useState(null);
    const [showTagTree, setShowTagTree] = useState(false);
    const [displayDraft, setDisplayDraft] = useState(filters.display || '');
    const [relationQuery, setRelationQuery] = useState('');
    const [relationResults, setRelationResults] = useState([]);
    const [relationEntity, setRelationEntity] = useState(null);
    const [relationType, setRelationType] = useState('');

    useEffect(() => {
        setDisplayDraft(filters.display || '');
    }, [filters.display]);

    useEffect(() => {
        if (!relationQuery) {
            setRelationResults([]);
            return;
        }

        const timeout = setTimeout(async () => {
            try {
                const resp = await api.fetch(`/api/search/?q=${encodeURIComponent(relationQuery)}`);
                const data = await resp.json();
                setRelationResults(Array.isArray(data) ? data.slice(0, 6) : []);
            } catch (error) {
                console.error('Failed to fetch relation entities', error);
                setRelationResults([]);
            }
        }, 300);

        return () => clearTimeout(timeout);
    }, [relationQuery]);

    const handleQueryChange = (e) => {
        setQuery(e.target.value);
    };

    const toggleArrayValue = (key, value) => {
        setFilters((prev) => {
            const current = prev[key] || [];
            const exists = current.includes(value);
            return {
                ...prev,
                [key]: exists ? current.filter((item) => item !== value) : [...current, value],
            };
        });
    };

    const openPanel = (panel) => {
        setShowTagTree(false);
        setActivePanel(panel);
    };

    const closePanels = () => {
        setActivePanel(null);
        setShowTagTree(false);
    };

    const applyDisplay = () => {
        setFilters((prev) => ({ ...prev, display: displayDraft }));
        closePanels();
    };

    const clearDisplay = () => {
        setDisplayDraft('');
        setFilters((prev) => ({ ...prev, display: '' }));
        closePanels();
    };

    const applyRelation = () => {
        if (!relationEntity || !relationType) return;
        setFilters((prev) => ({
            ...prev,
            relation: {
                entityId: relationEntity.id,
                entityDisplay: relationEntity.display || relationEntity.label,
                relationType,
            },
        }));
        closePanels();
    };

    const clearRelation = () => {
        setRelationQuery('');
        setRelationResults([]);
        setRelationEntity(null);
        setRelationType('');
        setFilters((prev) => ({ ...prev, relation: null }));
        closePanels();
    };

    const selectedSummary = useMemo(() => {
        const items = [];
        if (filters.primaryTag) items.push(`Tag: ${filters.primaryTag}`);
        if (filters.tags.length) items.push(`Tags: ${filters.tags.length}`);
        if (filters.types.length) items.push(`Types: ${filters.types.length}`);
        if (filters.display) items.push('Display contains');
        if (filters.relation) items.push('Relation');
        return items;
    }, [filters]);

    return (
        <div className="mb-5 space-y-3">
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

            {selectedSummary.length > 0 && (
                <div className="flex flex-wrap gap-2 text-xs text-gray-600 dark:text-gray-300">
                    {selectedSummary.map((item) => (
                        <span key={item} className="rounded-full bg-gray-200 dark:bg-gray-700 px-2 py-1">
                            {item}
                        </span>
                    ))}
                </div>
            )}

            <div className="flex flex-wrap gap-2 items-center">
                <button
                    className="rounded-full border border-gray-300 dark:border-gray-600 px-3 py-1 text-sm"
                    onClick={() => openPanel('tags')}
                >
                    Tags
                </button>
                <button
                    className="rounded-full border border-gray-300 dark:border-gray-600 px-3 py-1 text-sm"
                    onClick={() => openPanel('types')}
                >
                    Type
                </button>
                <button
                    className="rounded-full border border-gray-300 dark:border-gray-600 px-3 py-1 text-sm"
                    onClick={() => openPanel('display')}
                >
                    Display
                </button>
                <button
                    className="rounded-full border border-gray-300 dark:border-gray-600 px-3 py-1 text-sm"
                    onClick={() => openPanel('relations')}
                >
                    Relations
                </button>
                
                {/* Sort Icon with Dropdown Menu */}
                {sortBy !== undefined && setSortBy && setShowSortMenu && (
                    <div className="relative ml-auto">
                        <button
                            onClick={() => setShowSortMenu(!showSortMenu)}
                            className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                            title="Sort options"
                            aria-label="Sort options"
                        >
                            <svg className="w-5 h-5 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4" />
                            </svg>
                        </button>
                        
                        {/* Dropdown Menu */}
                        {showSortMenu && (
                        <>
                            {/* Backdrop to close menu */}
                            <div
                                className="fixed inset-0 z-10"
                                onClick={() => setShowSortMenu(false)}
                            />
                            
                            {/* Menu */}
                            <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-20 py-1">
                                <div className="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                                    Sort By
                                </div>
                                
                                {[
                                    { value: 'updated_at', label: 'Last Modified', icon: '🕐' },
                                    { value: 'created_at', label: 'Recently Created', icon: '✨' },
                                    { value: 'display', label: 'Name (A-Z)', icon: '🔤' },
                                    { value: 'display_desc', label: 'Name (Z-A)', icon: '🔤' },
                                    { value: 'type', label: 'Type', icon: '📑' },
                                ].map((option) => (
                                    <button
                                        key={option.value}
                                        onClick={() => {
                                            setSortBy(option.value);
                                            setShowSortMenu(false);
                                        }}
                                        className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center justify-between ${
                                            sortBy === option.value ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400' : 'text-gray-900 dark:text-gray-100'
                                        }`}
                                    >
                                        <span className="flex items-center gap-2">
                                            <span>{option.icon}</span>
                                            <span>{option.label}</span>
                                        </span>
                                        {sortBy === option.value && (
                                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                            </svg>
                                        )}
                                    </button>
                                ))}
                            </div>
                        </>
                    )}
                    </div>
                )}
            </div>

            {showTagTree && (
                <div className="fixed inset-0 z-40">
                    <button
                        className="absolute inset-0 bg-black/40"
                        onClick={closePanels}
                        aria-label="Close tag tree panel"
                    />
                    <TagTreePanel
                        key={`primary-tag-${filters.primaryTag || 'none'}`}
                        visible={showTagTree}
                        onClose={closePanels}
                        selectedTags={filters.primaryTag}
                        onTagsChange={(tag) => {
                            // Clear all filters and query, set only the selected primary tag
                            setQuery('');
                            setDisplayDraft('');
                            setRelationQuery('');
                            setRelationEntity(null);
                            setRelationType('');
                            setFilters({
                                primaryTag: tag,
                                tags: [],
                                types: [],
                                display: '',
                                relation: null,
                            });
                        }}
                        isPrimary={true}
                    />
                </div>
            )}

            {activePanel === 'tags' && (
                <div className="fixed inset-0 z-40 flex flex-col justify-end">
                    <button
                        className="flex-1 bg-black/40"
                        onClick={closePanels}
                        aria-label="Close filter panel"
                    />
                    <TagTreePanel
                        visible={activePanel === 'tags'}
                        onClose={closePanels}
                        selectedTags={filters.tags || []}
                        onTagsChange={(tags) => {
                            setFilters((prev) => ({
                                ...prev,
                                tags: tags,
                            }));
                        }}
                        isPrimary={false}
                    />
                </div>
            )}

            {activePanel && activePanel !== 'tags' && (
                <div className="fixed inset-0 z-40 flex flex-col justify-end">
                    <button
                        className="flex-1 bg-black/40"
                        onClick={closePanels}
                        aria-label="Close filter panel"
                    />
                    <div className="bg-white dark:bg-gray-800 rounded-t-2xl shadow-lg p-4 max-h-[70vh] overflow-y-auto">

                        {activePanel === 'types' && (
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-lg font-semibold">Types</h2>
                                    <button onClick={closePanels} className="text-gray-500 dark:text-gray-300">
                                        Done
                                    </button>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    {ENTITY_TYPES.map((type) => {
                                        const selected = filters.types.includes(type);
                                        return (
                                            <button
                                                key={type}
                                                onClick={() => toggleArrayValue('types', type)}
                                                className={`rounded-lg px-3 py-2 text-sm ${
                                                    selected
                                                        ? 'bg-blue-600 text-white'
                                                        : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100'
                                                }`}
                                            >
                                                {type}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {activePanel === 'display' && (
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-lg font-semibold">Display contains</h2>
                                    <button onClick={closePanels} className="text-gray-500 dark:text-gray-300">
                                        Close
                                    </button>
                                </div>
                                <input
                                    type="text"
                                    value={displayDraft}
                                    onChange={(e) => setDisplayDraft(e.target.value)}
                                    placeholder="Search display text..."
                                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-transparent px-3 py-2"
                                />
                                <div className="flex gap-2">
                                    <button
                                        onClick={applyDisplay}
                                        className="flex-1 rounded-lg bg-blue-600 text-white px-3 py-2"
                                    >
                                        Apply
                                    </button>
                                    <button
                                        onClick={clearDisplay}
                                        className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2"
                                    >
                                        Clear
                                    </button>
                                </div>
                            </div>
                        )}

                        {activePanel === 'relations' && (
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-lg font-semibold">Relations</h2>
                                    <button onClick={closePanels} className="text-gray-500 dark:text-gray-300">
                                        Close
                                    </button>
                                </div>
                                <div className="space-y-2">
                                    <label className="text-sm text-gray-600 dark:text-gray-300">
                                        Entity display name
                                    </label>
                                    <input
                                        type="text"
                                        value={relationQuery}
                                        onChange={(e) => {
                                            setRelationQuery(e.target.value);
                                            setRelationEntity(null);
                                        }}
                                        placeholder="Type a name..."
                                        className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-transparent px-3 py-2"
                                    />
                                    {relationResults.length > 0 && !relationEntity && (
                                        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                                            {relationResults.map((entity) => (
                                                <button
                                                    key={entity.id}
                                                    onClick={() => {
                                                        setRelationEntity(entity);
                                                        setRelationQuery(entity.display || entity.label || '');
                                                        setRelationResults([]);
                                                    }}
                                                    className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800"
                                                >
                                                    {entity.display || entity.label} · {entity.type}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm text-gray-600 dark:text-gray-300">
                                        Relation type
                                    </label>
                                    <select
                                        value={relationType}
                                        onChange={(e) => setRelationType(e.target.value)}
                                        className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-transparent px-3 py-2"
                                    >
                                        <option value="">Select relation...</option>
                                        {RELATION_TYPES.map((relation) => (
                                            <option key={relation} value={relation}>
                                                {relation}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div className="flex gap-2">
                                    <button
                                        onClick={applyRelation}
                                        className="flex-1 rounded-lg bg-blue-600 text-white px-3 py-2"
                                    >
                                        Apply
                                    </button>
                                    <button
                                        onClick={clearRelation}
                                        className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2"
                                    >
                                        Clear
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default SearchBar;
