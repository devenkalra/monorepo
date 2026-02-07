import React, { useState, useEffect } from 'react';
import api from '../services/api';

// Build a tree structure from flat tags
function buildTagTree(tags) {
    const tree = {};
    
    tags.forEach(tagObj => {
        const parts = tagObj.name.split('/');
        let current = tree;
        
        parts.forEach((part, index) => {
            if (!current[part]) {
                current[part] = {
                    name: part,
                    fullPath: parts.slice(0, index + 1).join('/'),
                    count: 0,
                    children: {}
                };
            }
            
            // Update count for this level
            if (index === parts.length - 1) {
                current[part].count = tagObj.count;
            }
            
            current = current[part].children;
        });
    });
    
    return tree;
}

// Recursive tree node component
function TreeNode({ node, selectedTags, onToggle, depth = 0, expandedPaths = [] }) {
    // Auto-expand if: depth < 2, OR this path is in expandedPaths, OR a child is selected
    const shouldAutoExpand = depth < 2 || 
                            expandedPaths.includes(node.fullPath) ||
                            selectedTags.some(tag => tag && tag.startsWith(node.fullPath + '/'));
    const [expanded, setExpanded] = useState(shouldAutoExpand);
    const hasChildren = Object.keys(node.children).length > 0;
    const isSelected = selectedTags.includes(node.fullPath);
    
    // Update expanded state when shouldAutoExpand changes
    React.useEffect(() => {
        if (shouldAutoExpand) {
            setExpanded(true);
        }
    }, [shouldAutoExpand]);
    
    return (
        <div className="select-none">
            <div 
                className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 ${
                    isSelected ? 'bg-blue-100 dark:bg-blue-900' : ''
                }`}
                style={{ paddingLeft: `${depth * 16 + 8}px` }}
            >
                {hasChildren && (
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            setExpanded(!expanded);
                        }}
                        className="w-4 h-4 flex items-center justify-center text-gray-500 dark:text-gray-400"
                    >
                        {expanded ? '▼' : '▶'}
                    </button>
                )}
                {!hasChildren && <span className="w-4" />}
                
                <button
                    onClick={() => onToggle(node.fullPath)}
                    className="flex-1 text-left"
                >
                    <span className={isSelected ? 'font-semibold text-blue-700 dark:text-blue-300' : ''}>
                        {node.name}
                    </span>
                    {node.count > 0 && (
                        <span className="ml-1 text-xs text-gray-500 dark:text-gray-400">
                            ({node.count})
                        </span>
                    )}
                </button>
            </div>
            
            {expanded && hasChildren && (
                <div>
                    {Object.values(node.children)
                        .sort((a, b) => a.name.localeCompare(b.name))
                        .map(child => (
                            <TreeNode
                                key={child.fullPath}
                                node={child}
                                selectedTags={selectedTags}
                                onToggle={onToggle}
                                depth={depth + 1}
                                expandedPaths={expandedPaths}
                            />
                        ))}
                </div>
            )}
        </div>
    );
}

function TagTreePanel({ visible, onClose, selectedTags, onTagsChange, isPrimary = false }) {
    const [tags, setTags] = useState([]);
    const [loading, setLoading] = useState(true);
    const [tree, setTree] = useState({});
    const [expandedPaths, setExpandedPaths] = useState([]);
    
    useEffect(() => {
        if (visible) {
            fetchTags();
        }
    }, [visible]);
    
    // Calculate paths to expand whenever selectedTags changes and tree is ready
    useEffect(() => {
        if (visible && selectedTags && Object.keys(tree).length > 0) {
            const tagsArray = Array.isArray(selectedTags) ? selectedTags : [selectedTags];
            const pathsToExpand = [];
            tagsArray.forEach(tag => {
                if (tag) {
                    const parts = tag.split('/');
                    // Add all parent paths
                    for (let i = 1; i < parts.length; i++) {
                        pathsToExpand.push(parts.slice(0, i).join('/'));
                    }
                }
            });
            setExpandedPaths(pathsToExpand);
        }
    }, [visible, selectedTags, tree]);
    
    const fetchTags = async () => {
        setLoading(true);
        try {
            // Fetch all tags (disable pagination with large limit)
            const resp = await api.fetch('/api/tags/?limit=1000');
            const data = await resp.json();
            // Handle paginated response
            const tagList = data.results || data;
            setTags(tagList);
            setTree(buildTagTree(tagList));
        } catch (error) {
            console.error('Failed to fetch tags', error);
            setTags([]);
            setTree({});
        } finally {
            setLoading(false);
        }
    };
    
    const handleToggle = (tagPath) => {
        if (isPrimary) {
            // For primary tag selection
            // If clicking the same tag, clear it (deselect)
            if (selectedTags === tagPath) {
                onTagsChange('');
            } else {
                onTagsChange(tagPath);
            }
            onClose();
        } else {
            // For multi-select
            if (selectedTags.includes(tagPath)) {
                onTagsChange(selectedTags.filter(t => t !== tagPath));
            } else {
                onTagsChange([...selectedTags, tagPath]);
            }
        }
    };
    
    if (!visible) return null;
    
    return (
        <div className={`fixed ${isPrimary ? 'left-0 top-0 bottom-0 w-80' : 'left-0 right-0 bottom-0 max-h-[70vh]'} bg-white dark:bg-gray-800 shadow-lg z-50 p-4 overflow-y-auto ${!isPrimary && 'rounded-t-2xl'}`}>
                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-semibold">
                        {isPrimary ? 'Select Primary Tag' : 'Select Tags (OR)'}
                    </h3>
                    <button 
                        onClick={onClose} 
                        className="text-gray-600 dark:text-gray-300 text-xl leading-none hover:text-gray-900 dark:hover:text-gray-100"
                    >
                        ✕
                    </button>
                </div>
                
                {loading ? (
                    <div className="text-center py-8 text-gray-500">Loading tags...</div>
                ) : Object.keys(tree).length === 0 ? (
                    <div className="text-center py-8 text-gray-500">No tags found</div>
                ) : (
                    <div className="space-y-1">
                        {Object.values(tree)
                            .sort((a, b) => a.name.localeCompare(b.name))
                            .map(node => (
                                <TreeNode
                                    key={node.fullPath}
                                    node={node}
                                    selectedTags={isPrimary ? (selectedTags ? [selectedTags] : []) : selectedTags}
                                    onToggle={handleToggle}
                                    depth={0}
                                    expandedPaths={expandedPaths}
                                />
                            ))}
                    </div>
                )}
            </div>
    );
}

export default TagTreePanel;
