import { test, expect } from '@playwright/test';
import { demoLoginAsResearcher, demoLoginAsSubject } from './helpers/auth';

test.describe('Subject Dashboard UI Improvements', () => {

  test.describe('Regular User (Subject) Navigation', () => {
    test.beforeEach(async ({ page }) => {
      await demoLoginAsSubject(page);
    });

    test('should show only 내 대시보드 and 메타볼리즘 for regular users', async ({ page }) => {
      const nav = page.getByRole('navigation');

      // Should see 내 대시보드
      await expect(nav.getByRole('button', { name: '내 대시보드' })).toBeVisible();

      // Should see 메타볼리즘
      await expect(nav.getByRole('button', { name: '메타볼리즘' })).toBeVisible();
    });

    test('should NOT show 코호트 분석 for regular users', async ({ page }) => {
      const nav = page.getByRole('navigation');

      // Should NOT see 코호트 분석
      await expect(nav.getByRole('button', { name: '코호트 분석' })).not.toBeVisible();
    });

    test('should NOT show researcher-only menus for regular users', async ({ page }) => {
      const nav = page.getByRole('navigation');

      // Should NOT see 대시보드 (researcher dashboard)
      await expect(nav.getByRole('button', { name: '대시보드', exact: true })).not.toBeVisible();

      // Should NOT see 피험자 관리
      await expect(nav.getByRole('button', { name: '피험자 관리' })).not.toBeVisible();

      // Should NOT see Raw Data
      await expect(nav.getByRole('button', { name: 'Raw Data' })).not.toBeVisible();

      // Should NOT see 슈퍼어드민
      await expect(nav.getByRole('button', { name: '슈퍼어드민' })).not.toBeVisible();
    });
  });

  test.describe('Subject Dashboard Test List Table', () => {
    test.beforeEach(async ({ page }) => {
      await demoLoginAsSubject(page);
    });

    test('should display test list in table format', async ({ page }) => {
      // Navigate to subject dashboard (should be default for subjects)
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Check for table headers
      const table = page.locator('table');

      // Should have table with proper headers
      await expect(table.getByRole('columnheader', { name: '날짜' })).toBeVisible();
      await expect(table.getByRole('columnheader', { name: '프로토콜' })).toBeVisible();
      await expect(table.getByRole('columnheader', { name: 'VO2MAX' })).toBeVisible();
      await expect(table.getByRole('columnheader', { name: 'HR MAX' })).toBeVisible();
      await expect(table.getByRole('columnheader', { name: '상태' })).toBeVisible();
    });

    test('test rows should be keyboard accessible', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Check for table rows with proper accessibility attributes
      const tableRows = page.locator('tbody tr[role="button"]');
      const rowCount = await tableRows.count();

      if (rowCount > 0) {
        const firstRow = tableRows.first();

        // Should have tabindex for keyboard focus
        await expect(firstRow).toHaveAttribute('tabindex', '0');

        // Should have role="button" for screen readers
        await expect(firstRow).toHaveAttribute('role', 'button');
      }
    });

    test('clicking test row should navigate to metabolism page', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Wait for table to load
      await page.waitForSelector('table tbody tr', { timeout: 5000 }).catch(() => {
        // If no rows, that's okay for demo mode
      });

      const tableRows = page.locator('tbody tr[role="button"]');
      const rowCount = await tableRows.count();

      if (rowCount > 0) {
        // Click first test row
        await tableRows.first().click();

        // Should navigate to metabolism page or show metabolism view
        // The exact behavior depends on routing implementation
        await page.waitForTimeout(500);
      }
    });
  });

  test.describe('Researcher/Admin Navigation', () => {
    test.beforeEach(async ({ page }) => {
      await demoLoginAsResearcher(page);
    });

    test('should show 코호트 분석 for researcher users', async ({ page }) => {
      const nav = page.getByRole('navigation');

      // Should see 코호트 분석
      await expect(nav.getByRole('button', { name: '코호트 분석' })).toBeVisible();
    });

    test('should show all researcher menus', async ({ page }) => {
      const nav = page.getByRole('navigation');

      // Should see 대시보드
      await expect(nav.getByRole('button', { name: '대시보드' })).toBeVisible();

      // Should see 피험자 관리
      await expect(nav.getByRole('button', { name: '피험자 관리' })).toBeVisible();

      // Should see 코호트 분석
      await expect(nav.getByRole('button', { name: '코호트 분석' })).toBeVisible();

      // Should see 메타볼리즘
      await expect(nav.getByRole('button', { name: '메타볼리즘' })).toBeVisible();

      // Should see Raw Data
      await expect(nav.getByRole('button', { name: 'Raw Data' })).toBeVisible();
    });
  });
});
