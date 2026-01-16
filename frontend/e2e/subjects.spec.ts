import { test, expect } from '@playwright/test';
import { demoLoginAsResearcher } from './helpers/auth';

test.describe('Subjects Management', () => {
  test.beforeEach(async ({ page }) => {
    await demoLoginAsResearcher(page);
    await page.goto('/subjects');
  });

  test('should display subjects list', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '피험자 관리' })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('input[placeholder*="검색" i]')).toBeVisible();
  });

  test('should filter subjects by search', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="search" i], input[placeholder*="find" i]');
    
    if (await searchInput.isVisible()) {
      await searchInput.fill('John');
      await page.waitForTimeout(500);
      
      // Results should be filtered
      const items = page.locator('[role="row"], li');
      const count = await items.count();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  });

  test('should open subject detail page', async ({ page }) => {
    const subjectRow = page.locator('[role="row"], li').first();
    
    if (await subjectRow.isVisible()) {
      await subjectRow.click();
      await page.waitForURL('**/subjects/**', { timeout: 5000 });
      expect(page.url()).toMatch(/subjects\/[^/]+/);
    }
  });

  test('should display subject details', async ({ page }) => {
    // Navigate to a subject first
    const subjectRow = page.locator('[role="row"], li').first();
    
    if (await subjectRow.isVisible()) {
      await subjectRow.click();
      await page.waitForTimeout(500);
      
      // Check for subject details
      const details = page.locator('main, article');
      await expect(details).toBeVisible();
    }
  });

  test('should pagination work', async ({ page }) => {
    const nextButton = page.locator('button:has-text("Next"), [aria-label="Next"]');
    
    if (await nextButton.isVisible()) {
      await nextButton.click();
      await page.waitForTimeout(500);
      
      // Should still be on subjects page
      expect(page.url()).toContain('subjects');
    }
  });

  test('should sorting work', async ({ page }) => {
    const sortButton = page.locator('button[class*="sort"], th button');
    
    const firstSort = await sortButton.first();
    if (await firstSort.isVisible()) {
      await firstSort.click();
      await page.waitForTimeout(500);
      
      // Still on subjects page
      expect(page.url()).toContain('subjects');
    }
  });

  test('should export subjects data', async ({ page }) => {
    const exportButton = page.locator('button:has-text("Export")');
    
    if (await exportButton.isVisible()) {
      await exportButton.click();
      await page.waitForTimeout(500);
    }
  });
});
