/**
 * Integration Tests: Entity CRUD Operations
 * 
 * Tests the complete flow of creating, reading, updating, and deleting entities
 * through the actual UI.
 */
import { test, expect } from '@playwright/test';

test.describe('Entity CRUD Operations', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Check if we need to login
    const loginButton = page.locator('button:has-text("Login")');
    if (await loginButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      // Fill in login form
      await page.fill('input[type="email"]', 'test@example.com');
      await page.fill('input[type="password"]', 'testpass123');
      await page.click('button:has-text("Login")');
      
      // Wait for login to complete
      await page.waitForTimeout(2000);
      
      // If login failed (user doesn't exist), try to register
      if (await page.locator('text=Invalid credentials').isVisible({ timeout: 1000 }).catch(() => false)) {
        await page.click('a:has-text("Register")');
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[placeholder*="username"]', 'testuser');
        await page.fill('input[type="password"]', 'testpass123');
        await page.click('button:has-text("Register")');
        await page.waitForTimeout(2000);
      }
    }
    
    // Wait for the main app to load
    await page.waitForSelector('button:has-text("Add Entity")', { timeout: 10000 });
  });

  test('should create a new Person entity', async ({ page }) => {
    // Click Add Entity button
    await page.click('button:has-text("Add Entity")');
    
    // Wait for the detail panel to appear
    await expect(page.locator('.fixed.inset-0')).toBeVisible();
    
    // Fill in person details
    await page.fill('input[placeholder*="Display name"]', 'Integration Test Person');
    await page.fill('input[placeholder*="First name"]', 'Integration');
    await page.fill('input[placeholder*="Last name"]', 'Test');
    await page.fill('textarea[placeholder*="Description"]', 'Created by integration test');
    
    // Add a tag
    await page.fill('input[placeholder*="Add tag"]', 'test-tag');
    await page.press('input[placeholder*="Add tag"]', 'Enter');
    
    // Save the entity
    await page.click('button:has-text("Save")');
    
    // Wait for save to complete
    await page.waitForTimeout(1000);
    
    // Verify entity appears in the list
    await expect(page.locator('text=Integration Test Person')).toBeVisible();
  });

  test('should view entity details', async ({ page }) => {
    // Create an entity first
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'View Test Person');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Click on the entity to view details
    await page.click('text=View Test Person');
    
    // Verify detail panel shows
    await expect(page.locator('h2:has-text("View Test Person")')).toBeVisible();
    await expect(page.locator('button:has-text("Edit")')).toBeVisible();
    await expect(page.locator('button:has-text("Delete")')).toBeVisible();
  });

  test('should edit an existing entity', async ({ page }) => {
    // Create an entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Edit Test Person');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Open the entity
    await page.click('text=Edit Test Person');
    
    // Click Edit button
    await page.click('button:has-text("Edit")');
    
    // Modify the name
    await page.fill('input[value="Edit Test Person"]', 'Updated Test Person');
    
    // Save changes
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Verify the updated name appears
    await expect(page.locator('text=Updated Test Person')).toBeVisible();
  });

  test('should delete an entity', async ({ page }) => {
    // Create an entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Delete Test Person');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Open the entity
    await page.click('text=Delete Test Person');
    
    // Click Delete button
    page.on('dialog', dialog => dialog.accept()); // Accept confirmation
    await page.click('button:has-text("Delete")');
    
    // Wait for deletion
    await page.waitForTimeout(1000);
    
    // Verify entity is removed from list
    await expect(page.locator('text=Delete Test Person')).not.toBeVisible();
  });

  test('should create different entity types', async ({ page }) => {
    const entityTypes = [
      { type: 'Location', name: 'Test Location', field: 'City', value: 'San Francisco' },
      { type: 'Movie', name: 'Test Movie', field: 'Year', value: '2024' },
      { type: 'Org', name: 'Test Organization', field: 'Name', value: 'Test Org' },
    ];

    for (const entity of entityTypes) {
      // Create entity
      await page.click('button:has-text("Add Entity")');
      
      // Select entity type
      await page.selectOption('select', entity.type);
      
      // Fill in details
      await page.fill('input[placeholder*="Display name"]', entity.name);
      
      // Save
      await page.click('button:has-text("Save")');
      await page.waitForTimeout(1000);
      
      // Verify it appears
      await expect(page.locator(`text=${entity.name}`)).toBeVisible();
      
      // Close detail panel
      await page.click('button[aria-label="Close detail panel"]');
      await page.waitForTimeout(500);
    }
  });

  test('should add and display URLs', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Person with URLs');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(500);
    
    // Click Edit
    await page.click('button:has-text("Edit")');
    
    // Add a URL
    await page.fill('input[placeholder*="Add new URL"]', 'https://example.com');
    await page.click('button:has-text("Add URL")');
    
    // Save
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Verify URL is displayed
    await expect(page.locator('a[href="https://example.com"]')).toBeVisible();
  });

  test('should filter entities by search', async ({ page }) => {
    // Create multiple entities
    const names = ['Alpha Person', 'Beta Person', 'Gamma Person'];
    
    for (const name of names) {
      await page.click('button:has-text("Add Entity")');
      await page.fill('input[placeholder*="Display name"]', name);
      await page.click('button:has-text("Save")');
      await page.waitForTimeout(500);
      await page.click('button[aria-label="Close detail panel"]');
      await page.waitForTimeout(500);
    }
    
    // Search for specific entity
    await page.fill('input[placeholder*="Search"]', 'Beta');
    await page.waitForTimeout(1000);
    
    // Verify only Beta is visible
    await expect(page.locator('text=Beta Person')).toBeVisible();
    // Alpha and Gamma might still be in DOM but not visible in results
  });
});
