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

  test("researcher dashboard shows analytics overview in its own tab", async ({
    page,
  }) => {
    await navigateAndWait(page, "/dashboard");

    await expect(page.locator("#filter-tabs")).toHaveCount(0);
    await expect(page.locator('a[href="/dashboard?tab=reports"]')).toBeVisible();
    await expect(page.locator("text=주요 지표 대시보드")).toBeVisible();
    await expect(page.locator("text=Current Cohort")).toBeVisible();
    await expect(page.locator("text=Repeat-Test Ready")).toBeVisible();
    await expect(page.locator("text=Cohort Areas")).toBeVisible();
    await expect(page.locator("text=Top VO2max")).toHaveCount(0);
  });

  test("subject drill-in renders trend signal, chart, and privacy-safe positioning", async ({
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
    await expect(detail.locator("text=시계열 변화 차트")).toBeVisible();
    await expect(detail.locator("text=코호트 좌표계")).toBeVisible();
    await expect(detail.locator("text=상위")).toHaveCount(2);
    await expect(detail.getByText("ΔFatMax 15.0")).toHaveCount(2);
    await expect(detail.getByText(/\d+\/\d+/)).toHaveCount(0);
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
        "text=A second usable anchor is needed before this subject gets a dashboard delta signal.",
      ),
    ).toBeVisible();
    await expect(page.locator("text=Unavailable")).toHaveCount(2);
  });
});
