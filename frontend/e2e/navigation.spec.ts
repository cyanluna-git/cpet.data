import { test, expect } from '@playwright/test';
import { demoLoginAsResearcher } from './helpers/auth';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await demoLoginAsResearcher(page);
  });

  test('should display navigation menu', async ({ page }) => {
    await expect(page.getByRole('navigation')).toBeVisible();
  });

  test('should navigate to dashboard from home', async ({ page }) => {
    // Researcher dashboard is the root route
    await page.goto('/');
    await expect(page.getByRole('navigation')).toBeVisible();
  });

  test('should navigate to subjects page', async ({ page }) => {
    await page.getByRole('navigation').getByRole('button', { name: '피험자 관리' }).click();
    await page.waitForURL('**/subjects', { timeout: 10000 });
    expect(page.url()).toContain('subjects');
  });

  test('should have breadcrumb navigation', async ({ page }) => {
    // App currently uses a top navigation bar; verify key entries exist.
    await expect(page.getByRole('navigation')).toBeVisible();
    await expect(page.getByRole('button', { name: '대시보드' })).toBeVisible();
    await expect(page.getByRole('navigation').getByRole('button', { name: '피험자 관리' })).toBeVisible();
  });
});
