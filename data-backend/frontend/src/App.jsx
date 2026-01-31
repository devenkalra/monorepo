import React, { useState, useEffect, useMemo } from 'react';
import EntityList from './components/EntityList';
import SearchBar from './components/SearchBar';
import ThemeToggle from './components/ThemeToggle';
import EntityDetail from './components/EntityDetail';
import UserMenu from './components/UserMenu';
import ConversationImport from './components/ConversationImport';
import api from './services/api';

function App() {
  const [entities, setEntities] = useState([]);
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState({
    primaryTag: '',
    tags: [],
    types: [],
    display: '',
    relation: null,
  });
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [initialViewMode, setInitialViewMode] = useState('details');
  const [sortBy, setSortBy] = useState('updated_at'); // default sort by last modified
  const [showSortMenu, setShowSortMenu] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const handleEntityClick = (entity) => {
    setInitialViewMode('details'); // Default to details view
    setSelectedEntity(entity);
    setShowDetail(true);
  };

  const handleCloseDetail = () => {
    setSelectedEntity(null);
    setShowDetail(false);
    setInitialViewMode('details'); // Reset to default
  };

  const handleEntityUpdate = (updatedEntity) => {
    // Check if this is a deletion request
    if (updatedEntity._deleted) {
      // Remove the entity from the list
      setEntities(prevEntities => 
        prevEntities.filter(entity => entity.id !== updatedEntity.id)
      );
      return;
    }

    // Check if this is a navigation request (clicking on related entity)
    if (updatedEntity._navigate) {
      // Remove the navigation flags
      const { _navigate, _viewMode, ...entityData } = updatedEntity;
      // Set the initial view mode if specified
      if (_viewMode) {
        setInitialViewMode(_viewMode);
      }
      // Load the new entity into the detail panel
      setSelectedEntity(null);
      setShowDetail(false);
      // Small delay to allow panel to close before opening with new entity
      setTimeout(() => {
        setSelectedEntity(entityData);
        setShowDetail(true);
      }, 100);
      return;
    }
    
    // Normal update: update the entity in the list
    setEntities(prevEntities => 
      prevEntities.map(entity => 
        entity.id === updatedEntity.id ? updatedEntity : entity
      )
    );
    // Update the selected entity so detail view shows latest data
    setSelectedEntity(updatedEntity);
  };

  const handleAddEntity = () => {
    // Create a blank entity object
    const blankEntity = {
      id: null, // Will be assigned by backend
      type: 'Person', // Default type
      label: '',
      display: '',
      description: '',
      tags: [],
      urls: [],
      photos: [],
      attachments: [],
      locations: [],
      // Person-specific fields
      first_name: '',
      last_name: '',
      dob: '',
      gender: '',
      emails: [],
      phones: [],
      profession: '',
      // Note-specific fields
      date: '',
      // Location-specific fields
      address1: '',
      address2: '',
      city: '',
      state: '',
      postal_code: '',
      country: '',
      // Movie-specific fields
      year: '',
      language: '',
      // Book-specific fields (shares year, language, country with Movie)
      summary: '',
      // Asset-specific fields
      value: '',
      acquired_on: '',
      // Org-specific fields
      name: '',
      kind: 'Unspecified',
      isNew: true // Flag to indicate this is a new entity
    };
    setInitialViewMode('details'); // Default to details view for new entities
    setSelectedEntity(blankEntity);
    setShowDetail(true);
  };

  const handleEntityCreate = (createdEntity) => {
    // Add the newly created entity to the list
    setEntities(prevEntities => [createdEntity, ...prevEntities]);
    // Update the selected entity with the created data
    setSelectedEntity(createdEntity);
  };

  const fetchEntities = async () => {
    const searchQuery = [query, filters.display].filter(Boolean).join(' ').trim();
    const tagSet = new Set(filters.tags);
    if (filters.primaryTag) tagSet.add(filters.primaryTag);
    const tagList = [...tagSet];
    const hasSearch =
      Boolean(searchQuery) ||
      tagList.length > 0 ||
      filters.types.length > 0 ||
      Boolean(filters.relation);

    const params = new URLSearchParams();
    let url = '/api/entities/recent/';
    if (!hasSearch) {
      params.append('limit', '20');
    } else {
      url = '/api/search/';
      if (searchQuery) params.append('q', searchQuery);
      if (filters.types.length) params.append('type', filters.types.join(','));
      if (tagList.length) params.append('tags', tagList.join(','));
      if (filters.relation) {
        params.append('relation_entity', filters.relation.entityId);
        params.append('relation_type', filters.relation.relationType);
      }
    }

    try {
      const resp = await api.fetch(`${url}?${params.toString()}`);
      const data = await resp.json();
      // Handle both paginated response {results: [...]} and array response [...]
      if (Array.isArray(data)) {
        setEntities(data);
      } else if (data && Array.isArray(data.results)) {
        setEntities(data.results);
      } else {
        setEntities([]);
      }
    } catch (error) {
      console.error('Failed to fetch entities', error);
      setEntities([]);
    }
  };

  useEffect(() => {
    fetchEntities();
  }, [query, filters]);

  // Sort entities based on selected sort option
  const sortedEntities = useMemo(() => {
    const sorted = [...entities];
    
    switch (sortBy) {
      case 'display':
        sorted.sort((a, b) => {
          const aName = (a.display || a.label || '').toLowerCase();
          const bName = (b.display || b.label || '').toLowerCase();
          return aName.localeCompare(bName);
        });
        break;
      case 'display_desc':
        sorted.sort((a, b) => {
          const aName = (a.display || a.label || '').toLowerCase();
          const bName = (b.display || b.label || '').toLowerCase();
          return bName.localeCompare(aName);
        });
        break;
      case 'type':
        sorted.sort((a, b) => a.type.localeCompare(b.type));
        break;
      case 'created_at':
        sorted.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        break;
      case 'updated_at':
      default:
        sorted.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
        break;
    }
    
    return sorted;
  }, [entities, sortBy]);

  const mobileHeader = useMemo(
    () => (
      <header className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="text-xl font-semibold">Entity Browser</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Recently updated entities
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <UserMenu />
        </div>
      </header>
    ),
    []
  );

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <div className="mx-auto w-full max-w-5xl p-4 pb-24">
        {mobileHeader}
        <SearchBar
          query={query}
          setQuery={setQuery}
          filters={filters}
          setFilters={setFilters}
          sortBy={sortBy}
          setSortBy={setSortBy}
          showSortMenu={showSortMenu}
          setShowSortMenu={setShowSortMenu}
        />
        
        {/* Entity Count */}
        <div className="mb-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {sortedEntities.length} {sortedEntities.length === 1 ? 'entity' : 'entities'}
          </p>
        </div>
        
        <EntityList 
          entities={sortedEntities} 
          onEntityClick={handleEntityClick}
        />
      </div>
      
      {/* Floating Action Buttons */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-3 z-30">
        {/* Import Conversations Button */}
        <button
          onClick={() => setShowImport(true)}
          className="w-14 h-14 bg-purple-600 text-white rounded-full shadow-lg hover:bg-purple-700 transition-all hover:scale-110 flex items-center justify-center"
          aria-label="Import conversations"
          title="Import conversations"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </button>
        
        {/* Add Entity Button */}
        <button
          onClick={handleAddEntity}
          className="w-14 h-14 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition-all hover:scale-110 flex items-center justify-center"
          aria-label="Add new entity"
          title="Add new entity"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>
      
      <EntityDetail
        entity={selectedEntity}
        isVisible={showDetail}
        onClose={handleCloseDetail}
        onUpdate={handleEntityUpdate}
        onCreate={handleEntityCreate}
        initialViewMode={initialViewMode}
      />
      
      {showImport && (
        <ConversationImport
          onClose={() => setShowImport(false)}
          onImportComplete={(result) => {
            // Optionally refresh entities list or show success message
            console.log('Import completed:', result);
          }}
        />
      )}
    </div>
  );
}

export default App;
