/**
 * Integration Tests: Entity Relations
 * 
 * Tests creating and managing relationships between entities through the UI.
 */
import { test, expect } from '@playwright/test';

test.describe('Entity Relations', () => {
  let person1Name, person2Name;

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
    
    // Create two people for relation tests
    person1Name = `Person A ${Date.now()}`;
    person2Name = `Person B ${Date.now()}`;
    
    // Create first person
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', person1Name);
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    await page.click('button[aria-label="Close detail panel"]');
    await page.waitForTimeout(500);
    
    // Create second person
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', person2Name);
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    await page.click('button[aria-label="Close detail panel"]');
    await page.waitForTimeout(500);
  });

  test('should create a relation between two people', async ({ page }) => {
    // Open first person
    await page.click(`text=${person1Name}`);
    
    // Switch to Relations tab
    await page.click('button:has-text("Relations")');
    await page.waitForTimeout(500);
    
    // Click Edit to enable relation editing
    await page.click('button:has-text("Edit")');
    await page.waitForTimeout(500);
    
    // Click Add Relation
    await page.click('button:has-text("+ Add Relation")');
    
    // Search for second person
    await page.fill('input[placeholder*="Type to search"]', person2Name.substring(0, 10));
    await page.waitForTimeout(1000);
    
    // Click on the search result
    await page.click(`text=${person2Name}`);
    
    // Select relation type
    await page.selectOption('select', 'IS_FRIEND_OF');
    
    // Click Add button
    await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
    await page.waitForTimeout(1000);
    
    // Save
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Verify relation appears
    await expect(page.locator(`text=${person2Name}`)).toBeVisible();
  });

  test('should display relation in both directions', async ({ page }) => {
    // Open first person and create relation
    await page.click(`text=${person1Name}`);
    await page.click('button:has-text("Relations")');
    await page.click('button:has-text("Edit")');
    await page.click('button:has-text("+ Add Relation")');
    await page.fill('input[placeholder*="Type to search"]', person2Name.substring(0, 10));
    await page.waitForTimeout(1000);
    await page.click(`text=${person2Name}`);
    await page.selectOption('select', 'IS_FRIEND_OF');
    await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
    await page.waitForTimeout(500);
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Close and open second person
    await page.click('button[aria-label="Close detail panel"]');
    await page.waitForTimeout(500);
    await page.click(`text=${person2Name}`);
    await page.click('button:has-text("Relations")');
    await page.waitForTimeout(500);
    
    // Verify reverse relation exists
    await expect(page.locator(`text=${person1Name}`)).toBeVisible();
  });

  test('should filter relations by search', async ({ page }) => {
    // Create multiple relations
    const thirdPerson = `Person C ${Date.now()}`;
    
    await page.click('button:has-text("Add Entity")');
    await page.fill('input[placeholder*="Display name"]', thirdPerson);
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    await page.click('button[aria-label="Close detail panel"]');
    await page.waitForTimeout(500);
    
    // Open first person and add two relations
    await page.click(`text=${person1Name}`);
    await page.click('button:has-text("Relations")');
    await page.click('button:has-text("Edit")');
    
    // Add first relation
    await page.click('button:has-text("+ Add Relation")');
    await page.fill('input[placeholder*="Type to search"]', person2Name.substring(0, 10));
    await page.waitForTimeout(1000);
    await page.click(`text=${person2Name}`);
    await page.selectOption('select', 'IS_FRIEND_OF');
    await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
    await page.waitForTimeout(500);
    
    // Add second relation
    await page.click('button:has-text("+ Add Relation")');
    await page.fill('input[placeholder*="Type to search"]', thirdPerson.substring(0, 10));
    await page.waitForTimeout(1000);
    await page.click(`text=${thirdPerson}`);
    await page.selectOption('select', 'IS_COLLEAGUE_OF');
    await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
    await page.waitForTimeout(500);
    
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Filter relations
    await page.fill('input[placeholder*="Filter entities"]', 'Person B');
    await page.waitForTimeout(500);
    
    // Verify only Person B is visible
    await expect(page.locator(`text=${person2Name}`)).toBeVisible();
  });

  test('should expand and collapse relation groups', async ({ page }) => {
    // Create relation
    await page.click(`text=${person1Name}`);
    await page.click('button:has-text("Relations")');
    await page.click('button:has-text("Edit")');
    await page.click('button:has-text("+ Add Relation")');
    await page.fill('input[placeholder*="Type to search"]', person2Name.substring(0, 10));
    await page.waitForTimeout(1000);
    await page.click(`text=${person2Name}`);
    await page.selectOption('select', 'IS_FRIEND_OF');
    await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
    await page.waitForTimeout(500);
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Click Collapse All
    await page.click('button:has-text("Collapse All")');
    await page.waitForTimeout(500);
    
    // Verify relations are hidden (the entity name should not be visible in relations section)
    const relationsSection = page.locator('section:has-text("Relations")');
    await expect(relationsSection.locator(`text=${person2Name}`)).not.toBeVisible();
    
    // Click Expand All
    await page.click('button:has-text("Expand All")');
    await page.waitForTimeout(500);
    
    // Verify relations are visible again
    await expect(relationsSection.locator(`text=${person2Name}`)).toBeVisible();
  });

  test('should delete a relation', async ({ page }) => {
    // Create relation
    await page.click(`text=${person1Name}`);
    await page.click('button:has-text("Relations")');
    await page.click('button:has-text("Edit")');
    await page.click('button:has-text("+ Add Relation")');
    await page.fill('input[placeholder*="Type to search"]', person2Name.substring(0, 10));
    await page.waitForTimeout(1000);
    await page.click(`text=${person2Name}`);
    await page.selectOption('select', 'IS_FRIEND_OF');
    await page.click('button:has-text("Add"):not(:has-text("Add Relation"))');
    await page.waitForTimeout(500);
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Enter edit mode again
    await page.click('button:has-text("Edit")');
    await page.waitForTimeout(500);
    
    // Find and click delete button for the relation
    const relationItem = page.locator(`text=${person2Name}`).locator('..').locator('..');
    await relationItem.locator('button[title="Remove relation"]').click();
    
    // Save
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(1000);
    
    // Verify relation is removed
    const relationsSection = page.locator('section:has-text("Relations")');
    await expect(relationsSection.locator(`text=${person2Name}`)).not.toBeVisible();
  });
});
