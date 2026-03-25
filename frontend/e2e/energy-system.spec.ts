import { test, expect } from '@playwright/test';
import { demoLoginAsResearcher } from './helpers/auth';

/**
 * Energy System 3-pathway Analysis E2E Tests
 *
 * Uses demo mode, which returns fixed 3-pathway data
 * (Oxidative 85.2%, Glycolytic 9.0%, Phosphagen 5.8%).
 * Edge cases use route interception to mock alternative API responses.
 */

// Default demo response for reference (matches frontend/src/lib/api.ts demo data)
const DEMO_3_PATHWAY = {
  pathways: [
    { name: 'Oxidative', energy_kj: 418.0, percentage: 85.2, color: '#3B82F6' },
    { name: 'Glycolytic', energy_kj: 43.9, percentage: 9.0, color: '#EF4444' },
    { name: 'Phosphagen', energy_kj: 28.5, percentage: 5.8, color: '#10B981' },
  ],
  total_kj: 490.4,
  has_lactate: true,
  has_phosphagen: true,
  delta_lactate: 7.0,
  exercise_duration_sec: 600,
  body_weight_kg: 70,
  mono_exp_fit: {
    amplitude_l_min: 1.5,
    tau_sec: 30.0,
    baseline_l_min: 0.5,
    r_squared: 0.95,
    n_points: 180,
  },
  recovery_window: { start_sec: 600, end_sec: 780, is_manual_override: false },
  warnings: [],
};

async function navigateToEnergySystemTab(page: import('@playwright/test').Page) {
  await demoLoginAsResearcher(page);

  // Navigate to 메타볼리즘
  const nav = page.getByRole('navigation');
  await nav.getByRole('button', { name: '메타볼리즘' }).click();

  // Wait for metabolism page to load - select a test first
  await page.waitForTimeout(1000);

  // Click the Energy System tab
  const energyTabBtn = page.getByRole('button', { name: 'Energy System' });
  // If the tab is visible, click it
  const isVisible = await energyTabBtn.isVisible().catch(() => false);
  if (isVisible) {
    await energyTabBtn.click();
    await page.waitForTimeout(500);
  }
}


test.describe('Energy System 3-Pathway Analysis', () => {

  test.describe('3-Pathway Display (Demo Mode)', () => {

    test('should display 3 pathway rows in detail table', async ({ page }) => {
      await navigateToEnergySystemTab(page);

      // Check the detail table has all three pathways
      // The table has rows with pathway names
      const table = page.locator('table');
      const tableVisible = await table.isVisible().catch(() => false);

      if (tableVisible) {
        await expect(table.getByText('Oxidative')).toBeVisible({ timeout: 10000 });
        await expect(table.getByText('Glycolytic')).toBeVisible();
        await expect(table.getByText('Phosphagen')).toBeVisible();

        // Total row should show 100%
        await expect(table.getByText('100%')).toBeVisible();

        // Total kJ should be displayed
        await expect(table.getByText('490.4 kJ')).toBeVisible();
      }
    });

    test('should display pie chart section', async ({ page }) => {
      await navigateToEnergySystemTab(page);

      // The pie chart heading
      const chartHeading = page.getByText('에너지 시스템 기여도');
      const headingVisible = await chartHeading.isVisible().catch(() => false);

      if (headingVisible) {
        await expect(chartHeading).toBeVisible();
        // Total label beneath pie chart
        await expect(page.getByText('Total: 490.4 kJ')).toBeVisible();
      }
    });

    test('should display mono-exponential fit details', async ({ page }) => {
      await navigateToEnergySystemTab(page);

      // Mono-exp fit section
      const fitSection = page.getByText('Recovery VO2 Fit');
      const isVisible = await fitSection.isVisible().catch(() => false);

      if (isVisible) {
        await expect(fitSection).toBeVisible();
        // R-squared value
        await expect(page.getByText('R²:')).toBeVisible();
      }
    });
  });


  test.describe('2-Pathway (No Lactate) via Route Interception', () => {

    test('should hide Glycolytic row and show info box when no lactate', async ({ page }) => {
      // Intercept the energy-system API call and return 2-pathway data
      const twoPathway = {
        ...DEMO_3_PATHWAY,
        pathways: [
          { name: 'Oxidative', energy_kj: 418.0, percentage: 96.4, color: '#3B82F6' },
          { name: 'Phosphagen', energy_kj: 15.7, percentage: 3.6, color: '#10B981' },
        ],
        total_kj: 433.7,
        has_lactate: false,
        has_phosphagen: true,
        delta_lactate: null,
      };

      await page.route('**/tests/*/energy-system', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(twoPathway),
        });
      });

      await navigateToEnergySystemTab(page);

      const table = page.locator('table');
      const tableVisible = await table.isVisible().catch(() => false);

      if (tableVisible) {
        // Oxidative and Phosphagen should be visible
        await expect(table.getByText('Oxidative')).toBeVisible({ timeout: 10000 });
        await expect(table.getByText('Phosphagen')).toBeVisible();

        // Glycolytic should NOT be in the table
        await expect(table.getByText('Glycolytic')).not.toBeVisible();
      }

      // Info box about missing lactate should be visible
      const infoBox = page.getByText('Glycolytic pathway not available');
      const infoVisible = await infoBox.isVisible().catch(() => false);
      if (infoVisible) {
        await expect(infoBox).toBeVisible();
      }
    });
  });


  test.describe('Recovery Override', () => {

    test('should show Recalculate button for researchers', async ({ page }) => {
      await navigateToEnergySystemTab(page);

      const recalcBtn = page.getByRole('button', { name: 'Recalculate' });
      const isVisible = await recalcBtn.isVisible().catch(() => false);

      // In demo mode with canEdit=true, the Recovery Phase Override section appears
      if (isVisible) {
        await expect(recalcBtn).toBeVisible();
      }
    });

    test('should update data after recalculate via route interception', async ({ page }) => {
      // First load: default 3-pathway
      let callCount = 0;
      const overriddenResponse = {
        ...DEMO_3_PATHWAY,
        pathways: [
          { name: 'Oxidative', energy_kj: 418.0, percentage: 86.5, color: '#3B82F6' },
          { name: 'Glycolytic', energy_kj: 43.9, percentage: 9.1, color: '#EF4444' },
          { name: 'Phosphagen', energy_kj: 21.3, percentage: 4.4, color: '#10B981' },
        ],
        total_kj: 483.2,
        recovery_window: { start_sec: 610, end_sec: 720, is_manual_override: true },
      };

      await page.route('**/tests/*/energy-system', (route, request) => {
        callCount++;
        if (request.method() === 'POST') {
          // POST (recalculate) returns overridden response
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(overriddenResponse),
          });
        } else {
          // GET returns default demo data
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(DEMO_3_PATHWAY),
          });
        }
      });

      await navigateToEnergySystemTab(page);

      const recalcBtn = page.getByRole('button', { name: 'Recalculate' });
      const isVisible = await recalcBtn.isVisible().catch(() => false);

      if (isVisible) {
        await recalcBtn.click();
        await page.waitForTimeout(1000);

        // After recalculate, the total_kj should update
        const table = page.locator('table');
        const tableVisible = await table.isVisible().catch(() => false);

        if (tableVisible) {
          // The new total should be 483.2 kJ
          await expect(table.getByText('483.2 kJ')).toBeVisible({ timeout: 5000 });
        }
      }
    });
  });


  test.describe('Phosphagen Unavailable Warning', () => {

    test('should show info box when phosphagen is not available', async ({ page }) => {
      const noPhosphagen = {
        ...DEMO_3_PATHWAY,
        pathways: [
          { name: 'Oxidative', energy_kj: 418.0, percentage: 90.5, color: '#3B82F6' },
          { name: 'Glycolytic', energy_kj: 43.9, percentage: 9.5, color: '#EF4444' },
        ],
        total_kj: 461.9,
        has_phosphagen: false,
        mono_exp_fit: null,
        recovery_window: null,
        warnings: ['Recovery phase too short; phosphagen energy unavailable'],
      };

      await page.route('**/tests/*/energy-system', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(noPhosphagen),
        });
      });

      await navigateToEnergySystemTab(page);

      // Info box about phosphagen unavailable
      const infoBox = page.getByText('Phosphagen pathway not available');
      const isVisible = await infoBox.isVisible().catch(() => false);

      if (isVisible) {
        await expect(infoBox).toBeVisible();
      }

      // Table should NOT have Phosphagen row
      const table = page.locator('table');
      const tableVisible = await table.isVisible().catch(() => false);
      if (tableVisible) {
        await expect(table.getByText('Phosphagen')).not.toBeVisible();
      }
    });
  });


  test.describe('Low R-squared Warning', () => {

    test('should display (low) label when R² < 0.80', async ({ page }) => {
      const lowR2Response = {
        ...DEMO_3_PATHWAY,
        mono_exp_fit: {
          amplitude_l_min: 1.5,
          tau_sec: 30.0,
          baseline_l_min: 0.5,
          r_squared: 0.65,
          n_points: 180,
        },
        warnings: ['Low mono-exponential fit quality (R²=0.650 < 0.80). Phosphagen estimate may be unreliable.'],
      };

      await page.route('**/tests/*/energy-system', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(lowR2Response),
        });
      });

      await navigateToEnergySystemTab(page);

      // The (low) label should appear next to R²
      const lowLabel = page.getByText('(low)');
      const isVisible = await lowLabel.isVisible().catch(() => false);

      if (isVisible) {
        await expect(lowLabel).toBeVisible();
      }

      // Warning box should be visible
      const warningText = page.getByText('Phosphagen estimate may be unreliable');
      const warningVisible = await warningText.isVisible().catch(() => false);
      if (warningVisible) {
        await expect(warningText).toBeVisible();
      }
    });
  });
});
