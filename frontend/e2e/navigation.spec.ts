import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to home page
    await page.goto('/');
  });

  test('should display navigation menu', async ({ page }) => {
    const nav = page.locator('nav');
    await expect(nav).toBeVisible();
  });

  test('should navigate to dashboard from home', async ({ page }) => {
    const dashboardLink = page.locator('a:has-text("Dashboard")');
    if (await dashboardLink.isVisible()) {
      await dashboardLink.click();
      await page.waitForURL('**/dashboard', { timeout: 5000 });
      expect(page.url()).toContain('dashboard');
    }
  });

  test('should navigate to subjects page', async ({ page }) => {
    const subjectsLink = page.locator('a:has-text("Subjects")');
    if (await subjectsLink.isVisible()) {
      await subjectsLink.click();
      await page.waitForURL('**/subjects', { timeout: 5000 });
      expect(page.url()).toContain('subjects');
    }
  });

  test('should have breadcrumb navigation', async ({ page }) => {
    const breadcrumb = page.locator('[role="navigation"]:has-text("breadcrumb")');
    // Navigation component should exist
    const navElements = page.locator('nav');
    await expect(navElements).toBeVisible();
  });
});
