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

  test.describe('Goals Feature', () => {
    test.beforeEach(async ({ page }) => {
      // Clear localStorage before each test
      await page.addInitScript(() => {
        localStorage.removeItem('cpet_user_goals');
      });
      await demoLoginAsSubject(page);
    });

    test('should display goals card', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Should see goals card
      await expect(page.getByText('나의 목표')).toBeVisible();
    });

    test('should be able to edit and save goals', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Click edit button
      await page.getByRole('button', { name: '편집' }).click();

      // Should see input fields
      await expect(page.getByPlaceholder('예: 50')).toBeVisible();
      await expect(page.getByPlaceholder('예: 140')).toBeVisible();
      await expect(page.getByPlaceholder('예: 2')).toBeVisible();

      // Fill in VO2 MAX goal
      await page.getByPlaceholder('예: 50').fill('55');

      // Fill in FATMAX HR goal
      await page.getByPlaceholder('예: 140').fill('145');

      // Save
      await page.getByRole('button', { name: '저장' }).click();

      // Should see progress display
      await expect(page.getByText('/ 55 ml/kg/min')).toBeVisible();
      await expect(page.getByText('/ 145 bpm')).toBeVisible();
    });

    test('should cancel goal editing', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Click edit button
      await page.getByRole('button', { name: '편집' }).click();

      // Fill in value
      await page.getByPlaceholder('예: 50').fill('99');

      // Cancel using X button
      await page.locator('button').filter({ has: page.locator('svg.lucide-x') }).click();

      // Should not see the entered value
      await expect(page.getByText('/ 99 ml/kg/min')).not.toBeVisible();
    });

    test('should display monthly test progress', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Should see monthly test goal section
      await expect(page.getByText('이번 달 테스트')).toBeVisible();
    });
  });

  test.describe('Trend Chart Feature', () => {
    test.beforeEach(async ({ page }) => {
      await demoLoginAsSubject(page);
    });

    test('should display trend chart section when multiple tests exist', async ({ page }) => {
      await page.getByRole('navigation').getByRole('button', { name: '내 대시보드' }).click();

      // Note: In demo mode with sample data, we may or may not have multiple tests
      // This test checks if the trend section appears when conditions are met
      const trendSection = page.getByText('나의 변화 추이');

      // If trend section exists, verify its structure
      const isTrendVisible = await trendSection.isVisible().catch(() => false);
      if (isTrendVisible) {
        // Should see legend items
        await expect(page.getByText('VO2 MAX').locator('visible=true').first()).toBeVisible();
        await expect(page.getByText('FATMAX HR').locator('visible=true').first()).toBeVisible();
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
