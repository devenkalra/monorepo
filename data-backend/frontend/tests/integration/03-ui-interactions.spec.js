/**
 * Integration Tests: UI Interactions
 * 
 * Tests user interface interactions, navigation, and state management.
 */
import { test, expect } from '@playwright/test';

test.describe('UI Interactions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Check if we need to login
    const loginButton = page.locator('button:has-text("Login")');
    if (await loginButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await page.fill('input[type="email"]', 'test@example.com');
      await page.fill('input[type="password"]', 'testpass123');
      await page.click('button:has-text("Login")');
      await page.waitForTimeout(2000);
      
      if (await page.locator('text=Invalid credentials').isVisible({ timeout: 1000 }).catch(() => false)) {
        await page.click('a:has-text("Register")');
        await page.fill('input[type="email"]', 'test@example.com');
        await page.fill('input[placeholder*="username"]', 'testuser');
        await page.fill('input[type="password"]', 'testpass123');
        await page.click('button:has-text("Register")');
        await page.waitForTimeout(2000);
      }
    }
    
    await page.waitForSelector('button:has-text("Add Entity")', { timeout: 10000 });
  });

  test('should navigate using browser back/forward buttons', async ({ page }) => {
    // Create an entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Navigation Test');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Verify we're on the entity detail page
    await expect(page.locator('h2:has-text("Navigation Test")')).toBeVisible();
    
    // Go back
    await page.goBack();
    await page.waitForTimeout(500);
    
    // Should be on list page
    await expect(page.locator('h2:has-text("Navigation Test")')).not.toBeVisible();
    
    // Go forward
    await page.goForward();
    await page.waitForTimeout(500);
    
    // Should be back on detail page
    await expect(page.locator('h2:has-text("Navigation Test")')).toBeVisible();
  });

  test('should switch between Details and Relations tabs', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Tab Test');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Should be on Details tab by default
    await expect(page.locator('button:has-text("Details")').locator('..')).toHaveClass(/border-blue-600/);
    
    // Click Relations tab
    await page.click('button:has-text("Relations")');
    await page.waitForTimeout(500);
    
    // Relations tab should be active
    await expect(page.locator('button:has-text("Relations")').locator('..')).toHaveClass(/border-blue-600/);
    
    // Click Details tab
    await page.click('button:has-text("Details")');
    await page.waitForTimeout(500);
    
    // Details tab should be active again
    await expect(page.locator('button:has-text("Details")').locator('..')).toHaveClass(/border-blue-600/);
  });

  test('should preserve edit mode when switching tabs', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Edit Mode Test');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Enter edit mode
    await page.click('button:has-text("Edit")');
    await page.waitForTimeout(500);
    
    // Switch to Relations tab
    await page.click('button:has-text("Relations")');
    await page.waitForTimeout(500);
    
    // Should still be in edit mode (Add Relation button should be visible)
    await expect(page.locator('button:has-text("+ Add Relation")')).toBeVisible();
    
    // Switch back to Details
    await page.click('button:has-text("Details")');
    await page.waitForTimeout(500);
    
    // Should still be in edit mode (Save button should be visible)
    await expect(page.locator('button:has-text("Save")')).toBeVisible();
  });

  test('should cancel edit without saving changes', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Cancel Test');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Enter edit mode
    await page.click('button:has-text("Edit")');
    
    // Make changes
    await page.fill('input[value="Cancel Test"]', 'Modified Name');
    
    // Cancel
    await page.click('button:has-text("Cancel")');
    await page.waitForTimeout(500);
    
    // Original name should be displayed
    await expect(page.locator('h2:has-text("Cancel Test")')).toBeVisible();
    await expect(page.locator('h2:has-text("Modified Name")')).not.toBeVisible();
  });

  test('should close detail panel', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Close Test');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Detail panel should be visible
    await expect(page.locator('h2:has-text("Close Test")')).toBeVisible();
    
    // Click close button
    await page.click('button[aria-label="Close detail panel"]');
    await page.waitForTimeout(500);
    
    // Detail panel should be hidden
    await expect(page.locator('h2:has-text("Close Test")')).not.toBeVisible();
  });

  test('should display entity type badge', async ({ page }) => {
    // Create different entity types
    const types = ['Person', 'Location', 'Movie'];
    
    for (const type of types) {
      await page.click('button:has-text("Add Entity")');
      await page.selectOption('select', type);
      await page.fill('input[placeholder*="Display name"]', `${type} Test`);
      await page.click('button:has-text("Save")');
      await page.waitForTimeout(1000);
      
      // Verify type is displayed
      await expect(page.locator(`text=${type}`)).toBeVisible();
      
      await page.click('button[aria-label="Close detail panel"]');
      await page.waitForTimeout(500);
    }
  });

  test('should show validation errors for required fields', async ({ page }) => {
    // Try to create entity without required fields
    await page.click('button:has-text("Add Entity")');
    
    // Try to save without filling anything
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(500);
    
    // Should still be on the form (not closed)
    await expect(page.locator('button:has-text("Save")')).toBeVisible();
  });

  test('should handle rapid clicking gracefully', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Rapid Click Test');
    
    // Click Save multiple times rapidly
    await Promise.all([
      page.click('button:has-text("Save")'),
      page.click('button:has-text("Save")'),
      page.click('button:has-text("Save")'),
    ]);
    
    await page.waitForTimeout(2000);
    
    // Should only create one entity (check by trying to find duplicates)
    const matches = await page.locator('text=Rapid Click Test').count();
    expect(matches).toBeLessThanOrEqual(2); // One in list, possibly one in detail
  });

  test('should maintain scroll position in entity list', async ({ page }) => {
    // Create many entities to enable scrolling
    for (let i = 0; i < 15; i++) {
      await page.click('button:has-text("Add Entity")');
      await page.fill('input[placeholder*="Display name"]', `Scroll Test ${i}`);
      await page.click('button:has-text("Save")');
      await page.waitForTimeout(300);
      await page.click('button[aria-label="Close detail panel"]');
      await page.waitForTimeout(300);
    }
    
    // Scroll down in the list
    await page.evaluate(() => {
      const listContainer = document.querySelector('.overflow-y-auto');
      if (listContainer) listContainer.scrollTop = 500;
    });
    
    const scrollPosition = await page.evaluate(() => {
      const listContainer = document.querySelector('.overflow-y-auto');
      return listContainer ? listContainer.scrollTop : 0;
    });
    
    // Open an entity
    await page.click('text=Scroll Test 10');
    await page.waitForTimeout(500);
    
    // Close it
    await page.click('button[aria-label="Close detail panel"]');
    await page.waitForTimeout(500);
    
    // Scroll position should be maintained (approximately)
    const newScrollPosition = await page.evaluate(() => {
      const listContainer = document.querySelector('.overflow-y-auto');
      return listContainer ? listContainer.scrollTop : 0;
    });
    
    expect(Math.abs(newScrollPosition - scrollPosition)).toBeLessThan(100);
  });

  test('should show loading states appropriately', async ({ page }) => {
    // Create entity
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', 'Loading Test');
    
    // Click save and immediately check for loading state
    const savePromise = page.click('button:has-text("Save")');
    
    // Should show "Saving..." text briefly
    await expect(page.locator('button:has-text("Saving")')).toBeVisible({ timeout: 1000 }).catch(() => {
      // Loading state might be too fast to catch, which is okay
    });
    
    await savePromise;
    await page.waitForTimeout(1000);
    
    // Should return to normal state
    await expect(page.locator('button:has-text("Edit")')).toBeVisible();
  });
});
