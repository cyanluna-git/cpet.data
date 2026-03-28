/**
 * tests/e2e/dashboard-analytics.spec.ts
 *
 * Dashboard analytics E2E tests for the researcher/admin flow.
 *
 * Prerequisites:
 *   - Test server running via `python tests/e2e/run_test_server.py`
 *   - Test session cookie available in .test-session-cookie
 */

import { expect, test } from "@playwright/test";

import { loginAsTestUser, navigateAndWait } from "./helpers";

test.describe("Dashboard analytics", () => {
  test.beforeEach(async ({ context }) => {
    await loginAsTestUser(context);
  });

  test("researcher dashboard shows analytics overview alongside report filters", async ({
    page,
  }) => {
    await navigateAndWait(page, "/dashboard");

    await expect(page.locator("#filter-tabs")).toBeVisible();
    await expect(page.locator("text=주요 지표 대시보드")).toBeVisible();
    await expect(page.locator("text=Current Cohort")).toBeVisible();
    await expect(page.locator("text=Repeat-Test Ready")).toBeVisible();
    await expect(page.locator("text=Cohort Leaders")).toBeVisible();
  });

  test("subject drill-in renders trend signal and cohort positioning", async ({
    page,
  }) => {
    await navigateAndWait(page, "/dashboard");

    const subjectSelect = page.locator(
      '#dashboard-analytics-region select[name="subject_id"]',
    );
    await subjectSelect.selectOption({ label: "Alpha Rider" });

    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/dashboard/analytics/subject") &&
        resp.status() === 200,
    );

    const detail = page.locator("#dashboard-analytics-subject-detail");
    await expect(detail.locator("text=Trend Signal")).toBeVisible();
    await expect(detail.locator("text=vs 2026-01-10")).toBeVisible();
    await expect(detail.locator("text=Cohort Positioning")).toBeVisible();
    await expect(detail.getByText("Front Pack")).toHaveCount(2);
    await expect(detail.getByText("ΔFatMax 15.0")).toHaveCount(2);
  });

  test("sparse subject shows stable empty-state messaging", async ({ page }) => {
    await navigateAndWait(page, "/dashboard");

    const subjectSelect = page.locator(
      '#dashboard-analytics-region select[name="subject_id"]',
    );
    await subjectSelect.selectOption({ label: "Sparse Rider" });

    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/dashboard/analytics/subject") &&
        resp.status() === 200,
    );

    await expect(page.locator("text=Trend Signal")).toBeVisible();
    await expect(
      page.locator(
        "text=A second usable CPET anchor is needed before this subject gets a dashboard delta signal.",
      ),
    ).toBeVisible();
    await expect(page.locator("text=Unavailable")).toHaveCount(2);
  });
});
