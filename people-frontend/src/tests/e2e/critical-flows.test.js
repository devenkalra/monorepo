/**
 * End-to-End Tests for Critical User Flows
 * 
 * These tests simulate real user interactions and test the full stack.
 * Run these against a test instance of the application.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';

const API_BASE = process.env.VITE_API_URL || 'http://localhost:8000';

describe('Critical User Flows - E2E', () => {
  let authToken;
  let testUserId;
  let createdEntities = [];

  beforeAll(async () => {
    // Create test user and authenticate
    const email = `test-${Date.now()}@example.com`;
    const password = 'testpass123';

    // Register user
    const registerResponse = await fetch(`${API_BASE}/api/auth/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!registerResponse.ok) {
      // User might already exist, try login
      const loginResponse = await fetch(`${API_BASE}/api/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'test@example.com', password: 'testpass123' }),
      });
      
      const loginData = await loginResponse.json();
      authToken = loginData.access;
    } else {
      const registerData = await registerResponse.json();
      authToken = registerData.access;
    }

    expect(authToken).toBeDefined();
  });

  afterAll(async () => {
    // Cleanup: delete all created entities
    for (const entity of createdEntities) {
      await fetch(`${API_BASE}/api/${entity.endpoint}/${entity.id}/`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${authToken}`,
        },
      });
    }
  });

  describe('Entity Creation Flow', () => {
    it('creates a Person entity with all fields', async () => {
      const personData = {
        type: 'Person',
        display: 'E2E Test Person',
        first_name: 'E2E',
        last_name: 'Test',
        description: 'Created by E2E test',
        profession: 'Tester',
        emails: ['e2e@example.com'],
        phones: ['+1234567890'],
        tags: ['test', 'e2e'],
        urls: [
          { url: 'https://example.com', caption: 'Website' }
        ],
      };

      const response = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(personData),
      });

      expect(response.ok).toBe(true);
      const data = await response.json();
      
      expect(data.display).toBe('E2E Test Person');
      expect(data.first_name).toBe('E2E');
      expect(data.tags).toContain('test');
      expect(data.urls).toHaveLength(1);

      createdEntities.push({ id: data.id, endpoint: 'people' });
    });

    it('creates entities of different types', async () => {
      const entities = [
        {
          endpoint: 'locations',
          data: {
            type: 'Location',
            display: 'E2E Test Location',
            city: 'Test City',
            state: 'TS',
          },
        },
        {
          endpoint: 'movies',
          data: {
            type: 'Movie',
            display: 'E2E Test Movie',
            year: 2024,
          },
        },
        {
          endpoint: 'orgs',
          data: {
            type: 'Org',
            display: 'E2E Test Org',
            name: 'Test Organization',
          },
        },
      ];

      for (const entity of entities) {
        const response = await fetch(`${API_BASE}/api/${entity.endpoint}/`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(entity.data),
        });

        expect(response.ok).toBe(true);
        const data = await response.json();
        createdEntities.push({ id: data.id, endpoint: entity.endpoint });
      }
    });
  });

  describe('Entity Update Flow', () => {
    it('updates an entity', async () => {
      // Create entity
      const createResponse = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'To Update',
          first_name: 'Update',
        }),
      });

      const created = await createResponse.json();
      createdEntities.push({ id: created.id, endpoint: 'people' });

      // Update entity
      const updateResponse = await fetch(`${API_BASE}/api/people/${created.id}/`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          display: 'Updated Person',
          profession: 'Updated Profession',
        }),
      });

      expect(updateResponse.ok).toBe(true);
      const updated = await updateResponse.json();
      
      expect(updated.display).toBe('Updated Person');
      expect(updated.profession).toBe('Updated Profession');
    });
  });

  describe('Relation Management Flow', () => {
    it('creates and deletes relations between entities', async () => {
      // Create two people
      const person1Response = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'Person 1',
          first_name: 'One',
        }),
      });

      const person2Response = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'Person 2',
          first_name: 'Two',
        }),
      });

      const person1 = await person1Response.json();
      const person2 = await person2Response.json();
      
      createdEntities.push({ id: person1.id, endpoint: 'people' });
      createdEntities.push({ id: person2.id, endpoint: 'people' });

      // Create relation
      const relationResponse = await fetch(`${API_BASE}/api/relations/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from_entity: person1.id,
          to_entity: person2.id,
          relation_type: 'IS_FRIEND_OF',
        }),
      });

      expect(relationResponse.ok).toBe(true);
      const relation = await relationResponse.json();

      // Verify relation exists
      const relationsResponse = await fetch(
        `${API_BASE}/api/people/${person1.id}/relations/`,
        {
          headers: { 'Authorization': `Bearer ${authToken}` },
        }
      );

      const relations = await relationsResponse.json();
      expect(relations.outgoing).toHaveLength(1);
      expect(relations.outgoing[0].relation_type).toBe('IS_FRIEND_OF');

      // Delete relation
      const deleteResponse = await fetch(`${API_BASE}/api/relations/${relation.id}/`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${authToken}` },
      });

      expect(deleteResponse.ok).toBe(true);
    });
  });

  describe('Search Flow', () => {
    it('searches and filters entities', async () => {
      // Create entities with specific tags
      const taggedPerson = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'Searchable Person',
          first_name: 'Searchable',
          tags: ['searchtest'],
        }),
      });

      const person = await taggedPerson.json();
      createdEntities.push({ id: person.id, endpoint: 'people' });

      // Search by name
      const searchResponse = await fetch(
        `${API_BASE}/api/search/?q=Searchable`,
        {
          headers: { 'Authorization': `Bearer ${authToken}` },
        }
      );

      expect(searchResponse.ok).toBe(true);
      const results = await searchResponse.json();
      
      const found = results.find(r => r.id === person.id);
      expect(found).toBeDefined();
      expect(found.display).toBe('Searchable Person');

      // Filter by type
      const typeFilterResponse = await fetch(
        `${API_BASE}/api/search/?type=Person`,
        {
          headers: { 'Authorization': `Bearer ${authToken}` },
        }
      );

      const typeResults = await typeFilterResponse.json();
      typeResults.forEach(result => {
        expect(result.type).toBe('Person');
      });
    });
  });

  describe('Import/Export Flow', () => {
    it('exports and re-imports data', async () => {
      // Create test entity
      const createResponse = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'Export Test',
          first_name: 'Export',
          tags: ['export-test'],
        }),
      });

      const created = await createResponse.json();
      createdEntities.push({ id: created.id, endpoint: 'people' });

      // Export data
      const exportResponse = await fetch(`${API_BASE}/api/entities/export/`, {
        headers: { 'Authorization': `Bearer ${authToken}` },
      });

      expect(exportResponse.ok).toBe(true);
      const exportData = await exportResponse.json();
      
      expect(exportData.entities).toBeDefined();
      expect(Array.isArray(exportData.entities)).toBe(true);

      // Verify our entity is in export
      const foundInExport = exportData.entities.find(e => e.id === created.id);
      expect(foundInExport).toBeDefined();
    });
  });

  describe('URL Management Flow', () => {
    it('adds and updates URLs on an entity', async () => {
      // Create entity with URLs
      const createResponse = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'URL Test Person',
          urls: [
            { url: 'https://example.com', caption: 'Website' },
            { url: 'https://github.com/test', caption: 'GitHub' },
          ],
        }),
      });

      const created = await createResponse.json();
      createdEntities.push({ id: created.id, endpoint: 'people' });

      expect(created.urls).toHaveLength(2);
      expect(created.urls[0].url).toBe('https://example.com');

      // Update URLs
      const updateResponse = await fetch(`${API_BASE}/api/people/${created.id}/`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          urls: [
            { url: 'https://example.com', caption: 'Updated Website' },
          ],
        }),
      });

      const updated = await updateResponse.json();
      expect(updated.urls).toHaveLength(1);
      expect(updated.urls[0].caption).toBe('Updated Website');
    });
  });

  describe('Error Handling Flow', () => {
    it('handles invalid entity type gracefully', async () => {
      const response = await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'InvalidType',
          display: 'Invalid',
        }),
      });

      // Should either reject or handle gracefully
      expect([400, 422]).toContain(response.status);
    });

    it('handles invalid relation type', async () => {
      // Create two entities
      const person1 = await (await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'Person A',
        }),
      })).json();

      const person2 = await (await fetch(`${API_BASE}/api/people/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'Person',
          display: 'Person B',
        }),
      })).json();

      createdEntities.push({ id: person1.id, endpoint: 'people' });
      createdEntities.push({ id: person2.id, endpoint: 'people' });

      // Try invalid relation
      const response = await fetch(`${API_BASE}/api/relations/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from_entity: person1.id,
          to_entity: person2.id,
          relation_type: 'INVALID_RELATION',
        }),
      });

      expect(response.status).toBe(400);
    });
  });
});
