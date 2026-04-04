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
    await expect(page.locator("text=코호트 운영 개요")).toBeVisible();
    await expect(page.locator("text=현재 분석 가능 피험자")).toBeVisible();
    await expect(page.locator("text=반복 측정 해석 가능")).toBeVisible();
    await expect(page.locator("text=코호트 분포 요약")).toBeVisible();
    await expect(page.locator(".analytics-subject-shell .analytics-panel-label").filter({ hasText: "개별 피험자 보기" })).toBeVisible();
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
    await expect(detail.locator("text=반복 측정 추세")).toBeVisible();
    await expect(detail.locator("text=vs 2026-01-10")).toBeVisible();
    await expect(detail.locator("text=Cohort Positioning")).toBeVisible();
    await expect(detail.locator("text=연료 전략 프로필")).toBeVisible();
    await expect(detail.locator("text=현재 연료 전략")).toBeVisible();
    await expect(detail.locator("text=시계열 변화 차트")).toBeVisible();
    await expect(detail.locator("text=코호트 내 현재 위치")).toBeVisible();
    await expect(
      detail.locator("text=오른쪽일수록 현재 유산소 능력이 높고, 위쪽일수록 최근 변화 폭이 큽니다."),
    ).toBeVisible();
    await expect(detail.locator("[data-dashboard-chart-select]")).toHaveCount(0);
    await expect(detail.locator("[data-dashboard-chart-root]")).toHaveCount(3);
    await expect(detail.locator("[data-dashboard-map-root]")).toHaveCount(2);
    await expect(detail.locator("text=현재 상태 카드")).toHaveCount(0);
    await expect(detail.getByText(/코호트 내 백분위/)).toHaveCount(2);
    await expect(detail.getByText("ΔFatMax 15.0")).toHaveCount(2);
    await expect(detail.getByText(/\d+\/\d+/)).toHaveCount(0);
  });

  test("single-anchor subject shows current-state framing instead of time-series framing", async ({
    page,
  }) => {
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

    const detail = page.locator("#dashboard-analytics-subject-detail");
    await expect(detail.locator("text=현재 상태 요약")).toBeVisible();
    await expect(detail.locator("text=변화 해석 준비도")).toBeVisible();
    await expect(detail.locator("text=코호트 내 현재 위치 맵")).toBeVisible();
    await expect(detail.locator("text=현재 해석")).toBeVisible();
    await expect(detail.locator("text=다음 측정 권장")).toBeVisible();
    await expect(
      detail.locator(
        "text=변화 신호를 보려면 비교 가능한 측정이 한 번 더 필요합니다.",
      ),
    ).toHaveCount(0);
    await expect(detail.locator("text=시계열 변화 차트")).toHaveCount(0);
    await expect(detail.locator("text=Trend Signal")).toHaveCount(0);
    await expect(detail.locator("text=Unavailable")).toHaveCount(2);
    await expect(detail.locator("[data-dashboard-chart-select]")).toHaveCount(0);
    await expect(detail.locator("[data-dashboard-chart-root]")).toHaveCount(0);
    await expect(detail.locator("text=연료 전략 프로필")).toHaveCount(0);
    await expect(detail.locator("[data-dashboard-map-root]")).toHaveCount(1);
  });

  test("inscyd subject shows anaerobic profile map only when vlamax is available", async ({
    page,
  }) => {
    await navigateAndWait(page, "/dashboard");

    const subjectSelect = page.locator(
      '#dashboard-analytics-region select[name="subject_id"]',
    );
    await subjectSelect.selectOption({ label: "INSCYD Rider" });

    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/dashboard/analytics/subject") &&
        resp.status() === 200,
    );

    const detail = page.locator("#dashboard-analytics-subject-detail");
    await expect(detail.locator("text=무산소 프로필")).toBeVisible();
    await expect(detail.locator("text=연료 전략 프로필")).toBeVisible();
    await expect(detail.locator("text=현재 무산소 성향")).toBeVisible();
    await expect(detail.getByText("고강도 활용", { exact: true })).toBeVisible();
    await expect(detail.locator("[data-dashboard-map-root]")).toHaveCount(3);
  });
});
