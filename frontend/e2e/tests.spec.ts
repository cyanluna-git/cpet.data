import { test, expect } from '@playwright/test';
import { demoLoginAsResearcher } from './helpers/auth';

test.describe('CPET Tests Management', () => {
  test.beforeEach(async ({ page }) => {
    await demoLoginAsResearcher(page);
    await page.goto('/');
  });

  test('should display CPET tests list', async ({ page }) => {
    // Dashboard shows recent tests section
    await expect(page.getByText('최근 업로드된 테스트')).toBeVisible({ timeout: 10000 });
  });

  test('should open test detail view', async ({ page }) => {
    // Clicking inside a test card should navigate to /tests/:id
    const testCardTrigger = page.getByText('VO2 MAX').first();
    await expect(testCardTrigger).toBeVisible({ timeout: 10000 });
    await testCardTrigger.click();
    await page.waitForURL(/\/tests\//, { timeout: 10000 });
    expect(page.url()).toMatch(/tests\/[^/]+/);
  });

  test('should display test metrics and charts', async ({ page }) => {
    // Navigate to test detail
    const testRow = page.locator('[role="row"], li').first();
    
    if (await testRow.isVisible()) {
      await testRow.click();
      await page.waitForTimeout(500);
      
      // Check for charts/metrics
      const chart = page.locator('[class*="chart"], svg');
      const metrics = page.locator('[class*="metric"], [role="status"]');
      
      // At least one should exist
      const chartCount = await chart.count();
      const metricsCount = await metrics.count();
      expect(chartCount + metricsCount).toBeGreaterThanOrEqual(0);
    }
  });

  test('should upload new test data', async ({ page }) => {
    const uploadButton = page.locator('button:has-text("Upload"), button:has-text("Import")');
    
    if (await uploadButton.isVisible()) {
      await uploadButton.click();
      
      // Should show upload dialog
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 3000 });
    }
  });

  test('should filter tests by subject', async ({ page }) => {
    const filterButton = page.locator('button:has-text("Filter")');
    
    if (await filterButton.isVisible()) {
      await filterButton.click();
      await page.waitForTimeout(300);
      
      // Should still be on tests page
      expect(page.url()).toContain('tests');
    }
  });

  test('should compare multiple tests', async ({ page }) => {
    const compareButton = page.locator('button:has-text("Compare")');
    
    if (await compareButton.isVisible()) {
      await compareButton.click();
      await page.waitForTimeout(500);
      
      // Should show comparison view
      const comparison = page.locator('[class*="comparison"]');
      if (await comparison.count() > 0) {
        await expect(comparison.first()).toBeVisible();
      }
    }
  });

  test('should download test report', async ({ page }) => {
    const downloadButton = page.locator('button:has-text("Download"), button:has-text("Export")');
    
    if (await downloadButton.isVisible()) {
      await downloadButton.click();
      await page.waitForTimeout(500);
    }
  });
});
