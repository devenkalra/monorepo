/**
 * Component Tests for EntityDetail
 * 
 * Tests the EntityDetail component functionality including:
 * - Entity display
 * - Edit mode
 * - Relations management
 * - URL/Photo/Attachment handling
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import EntityDetail from '../components/EntityDetail';

// Mock the API
vi.mock('../services/api', () => ({
  default: {
    fetch: vi.fn(),
  },
}));

import api from '../services/api';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ id: 'test-id' }),
  };
});

describe('EntityDetail Component', () => {
  const mockEntity = {
    id: 'test-id',
    type: 'Person',
    display: 'John Doe',
    description: 'Test person',
    first_name: 'John',
    last_name: 'Doe',
    tags: ['friend', 'colleague'],
    urls: [
      { url: 'https://example.com', caption: 'Website' }
    ],
    photos: [],
    attachments: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  };

  const mockRelations = {
    outgoing: [
      {
        id: 'rel-1',
        relation_type: 'IS_FRIEND_OF',
        entity: {
          id: 'person-2',
          type: 'Person',
          display: 'Jane Smith',
        },
      },
    ],
    incoming: [],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders entity details correctly', () => {
    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0);
    expect(screen.getByText('Test person')).toBeInTheDocument();
  });

  it('switches to edit mode when Edit button is clicked', async () => {
    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    const editButton = screen.getByRole('button', { name: /edit/i });
    fireEvent.click(editButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });
  });

  it('displays URLs correctly', () => {
    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    expect(screen.getByText('Website')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Website/i });
    expect(link).toHaveAttribute('href', 'https://example.com');
  });

  it('switches between Details and Relations tabs', async () => {
    // Mock relations API call
    api.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockRelations,
    });

    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    const relationsTab = screen.getByRole('button', { name: /relations/i });
    fireEvent.click(relationsTab);

    await waitFor(() => {
      expect(screen.getByText(/IS_FRIEND_OF/i)).toBeInTheDocument();
    });
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();

    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={onClose}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    const closeButton = screen.getByRole('button', { name: /close detail panel/i });
    fireEvent.click(closeButton);

    expect(onClose).toHaveBeenCalled();
  });

  it('updates entity when Save is clicked', async () => {
    const onUpdate = vi.fn();
    
    // Mock successful update
    api.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ...mockEntity, display: 'John A. Doe' }),
    });

    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={onUpdate}
        />
      </BrowserRouter>
    );

    // Enter edit mode
    const editButton = screen.getByRole('button', { name: /edit/i });
    fireEvent.click(editButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
    });

    // Modify display name
    const displayInput = screen.getByDisplayValue('John Doe');
    fireEvent.change(displayInput, { target: { value: 'John A. Doe' } });

    // Save
    const saveButton = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/people/'),
        expect.objectContaining({
          method: 'PATCH',
        })
      );
    });
  });

  it('cancels edit mode without saving', async () => {
    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    // Enter edit mode
    const editButton = screen.getByRole('button', { name: /edit/i });
    fireEvent.click(editButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    // Modify display name
    const displayInput = screen.getByDisplayValue('John Doe');
    fireEvent.change(displayInput, { target: { value: 'Modified Name' } });

    // Cancel
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    // Should revert to original value
    await waitFor(() => {
      expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0);
      expect(screen.queryByText('Modified Name')).not.toBeInTheDocument();
    });
  });

  it('filters relations by search query', async () => {
    const relationsWithMultiple = {
      outgoing: [
        {
          id: 'rel-1',
          relation_type: 'IS_FRIEND_OF',
          entity: { id: '1', type: 'Person', display: 'Alice Smith' },
        },
        {
          id: 'rel-2',
          relation_type: 'IS_FRIEND_OF',
          entity: { id: '2', type: 'Person', display: 'Bob Jones' },
        },
        {
          id: 'rel-3',
          relation_type: 'IS_FRIEND_OF',
          entity: { id: '3', type: 'Person', display: 'Charlie Brown' },
        },
      ],
      incoming: [],
    };

    api.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => relationsWithMultiple,
    });

    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    // Switch to relations tab
    const relationsTab = screen.getByRole('button', { name: /relations/i });
    fireEvent.click(relationsTab);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    // Filter by "Alice"
    const filterInput = screen.getByPlaceholderText(/filter entities/i);
    fireEvent.change(filterInput, { target: { value: 'Alice' } });

    // Should show Alice but not Bob or Charlie
    expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    expect(screen.queryByText('Bob Jones')).not.toBeInTheDocument();
    expect(screen.queryByText('Charlie Brown')).not.toBeInTheDocument();
  });

  it('expands and collapses all relations', async () => {
    const relationsWithMultipleTypes = {
      outgoing: [
        {
          id: 'rel-1',
          relation_type: 'IS_FRIEND_OF',
          entity: { id: '1', type: 'Person', display: 'Alice Smith' },
        },
        {
          id: 'rel-2',
          relation_type: 'LIVES_AT',
          entity: { id: '2', type: 'Location', display: 'San Francisco' },
        },
      ],
      incoming: [],
    };

    api.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => relationsWithMultipleTypes,
    });

    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    // Switch to relations tab
    const relationsTab = screen.getByRole('button', { name: /relations/i });
    fireEvent.click(relationsTab);

    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });

    // Collapse all
    const collapseButton = screen.getByRole('button', { name: /collapse all/i });
    fireEvent.click(collapseButton);

    // Relations should be hidden
    await waitFor(() => {
      expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument();
    });

    // Expand all
    const expandButton = screen.getByRole('button', { name: /expand all/i });
    fireEvent.click(expandButton);

    // Relations should be visible again
    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    });
  });

  it('handles new entity creation', () => {
    const newEntity = {
      id: 'new',
      type: 'Person',
      display: '',
      isNew: true,
    };

    render(
      <BrowserRouter>
        <EntityDetail
          entity={newEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={vi.fn()}
        />
      </BrowserRouter>
    );

    // Should be in edit mode
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
  });

  it('deletes entity when Delete button is clicked', async () => {
    const onUpdate = vi.fn();
    
    // Mock confirm dialog
    global.confirm = vi.fn(() => true);
    
    // Mock successful delete
    api.fetch.mockResolvedValueOnce({
      ok: true,
    });

    render(
      <BrowserRouter>
        <EntityDetail
          entity={mockEntity}
          isVisible={true}
          onClose={vi.fn()}
          onUpdate={onUpdate}
        />
      </BrowserRouter>
    );

    const deleteButton = screen.getByRole('button', { name: /delete/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(api.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/people/'),
        expect.objectContaining({
          method: 'DELETE',
        })
      );
      expect(onUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          _deleted: true,
        })
      );
    });
  });
});
