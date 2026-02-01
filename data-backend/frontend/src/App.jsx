import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import EntityList from './components/EntityList';
import SearchBar from './components/SearchBar';
import ThemeToggle from './components/ThemeToggle';
import EntityDetail from './components/EntityDetail';
import UserMenu from './components/UserMenu';
import ConversationImport from './components/ConversationImport';
import api from './services/api';

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  
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

  // Handle URL changes (back/forward navigation)
  useEffect(() => {
    const path = location.pathname;
    const entityIdMatch = path.match(/^\/entity\/([^\/]+)/);
    // Extract view mode: can be 'details', 'relations', 'edit', or 'relations-edit'
    // Handles: /entity/:id, /entity/:id/edit, /entity/:id/relations, /entity/:id/relations/edit
    let viewMode = 'details';
    if (path.includes('/relations/edit')) {
      viewMode = 'relations-edit';
    } else if (path.includes('/relations')) {
      viewMode = 'relations';
    } else if (path.endsWith('/edit')) {
      viewMode = 'edit';
    }
    
    if (path === '/import') {
      setShowImport(true);
      setShowDetail(false);
    } else if (entityIdMatch) {
      const entityId = entityIdMatch[1];
      // Load entity if not already loaded or different
      if (!selectedEntity || selectedEntity.id !== entityId) {
        loadEntityById(entityId, viewMode);
      } else {
        // Same entity, just update view mode without reloading
        setInitialViewMode(viewMode);
        if (!showDetail) {
          setShowDetail(true);
        }
      }
    } else if (path === '/' || path === '') {
      // Home page - close detail view
      if (showDetail) {
        setShowDetail(false);
        setSelectedEntity(null);
      }
      if (showImport) {
        setShowImport(false);
      }
    }
    
    // Handle search query from URL
    const searchQuery = searchParams.get('q');
    if (searchQuery && searchQuery !== query) {
      setQuery(searchQuery);
    }
  }, [location.pathname, searchParams]);

  // Load entity by ID from API
  const loadEntityById = async (entityId, viewMode = 'details') => {
    if (entityId === 'new') {
      // Don't try to load 'new' entity from API
      return;
    }
    
    try {
      const response = await api.fetch(`/api/entities/${entityId}/`);
      if (!response.ok) {
        throw new Error('Failed to load entity');
      }
      const entityData = await response.json();
      setSelectedEntity(entityData);
      setInitialViewMode(viewMode);
      setShowDetail(true);
    } catch (error) {
      console.error('Error loading entity:', error);
      // If entity not found, navigate back to home
      navigate('/');
    }
  };

  const handleEntityClick = (entity) => {
    setInitialViewMode('details'); // Default to details view
    setSelectedEntity(entity);
    setShowDetail(true);
    // Update URL
    navigate(`/entity/${entity.id}`);
  };

  const handleCloseDetail = () => {
    setSelectedEntity(null);
    setShowDetail(false);
    setInitialViewMode('details'); // Reset to default
    // Navigate back to home
    navigate('/');
  };

  const handleEntityUpdate = (updatedEntity) => {
    // Check if this is a deletion request
    if (updatedEntity._deleted) {
      // Remove the entity from the list
      setEntities(prevEntities => 
        prevEntities.filter(entity => entity.id !== updatedEntity.id)
      );
      // Navigate back to home after deletion
      navigate('/');
      return;
    }

    // Check if this is a navigation request (clicking on related entity)
    if (updatedEntity._navigate) {
      // Remove the navigation flags
      const { _navigate, _viewMode, ...entityData } = updatedEntity;
      // Set the initial view mode if specified
      const viewMode = _viewMode || 'details';
      
      // Navigate to the new entity with appropriate view mode
      // The URL effect will handle loading the entity
      const viewPath = viewMode === 'details' ? '' : `/${viewMode}`;
      navigate(`/entity/${entityData.id}${viewPath}`);
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
      id: 'new', // Temporary ID for new entity
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
    // Navigate to new entity URL
    navigate('/entity/new/edit');
  };

  const handleEntityCreate = (createdEntity) => {
    // Add the newly created entity to the list
    setEntities(prevEntities => [createdEntity, ...prevEntities]);
    // Update the selected entity with the created data
    setSelectedEntity(createdEntity);
    // Navigate to the created entity's URL
    navigate(`/entity/${createdEntity.id}`);
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

  // Update URL when search query changes
  useEffect(() => {
    if (query && !location.pathname.startsWith('/entity/')) {
      navigate(`/?q=${encodeURIComponent(query)}`, { replace: true });
    } else if (!query && searchParams.get('q')) {
      navigate('/', { replace: true });
    }
  }, [query]);

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
          onClick={() => {
            setShowImport(true);
            navigate('/import');
          }}
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
          onClose={() => {
            setShowImport(false);
            navigate('/');
          }}
          onImportComplete={(result) => {
            // Optionally refresh entities list or show success message
            console.log('Import completed:', result);
            fetchEntities(); // Refresh the list
          }}
        />
      )}
    </div>
  );
}

export default App;
