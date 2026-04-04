import { expect, test } from "@playwright/test";
import { resolve } from "path";

import { loginAsTestUser, navigateAndWait } from "./helpers";

const INSCYD_RAW_DIR = resolve(__dirname, "..", "fixtures", "inscyd_ppd", "raw");

test.describe("INSCYD upload flow", () => {
  test.beforeEach(async ({ context }) => {
    await loginAsTestUser(context);
  });

  test("researcher can upload standalone INSCYD files and open the published interpretation report", async ({
    page,
  }) => {
    await navigateAndWait(page, "/upload");

    await page.locator("#subject_id").selectOption({ label: "INSCYD Rider" });
    await page.locator("#subject_name").fill("Geunyun Park");
    await page.locator("#test_date").fill("2026-04-04");
    await page.locator("#description").fill("Standalone INSCYD upload E2E");
    await page.locator("#file-input").setInputFiles([
      resolve(INSCYD_RAW_DIR, "KY Park_2026.pdf"),
      resolve(INSCYD_RAW_DIR, "2026-01-06-09-35-14.fit"),
      resolve(INSCYD_RAW_DIR, "2026-01-06-10-29-23.fit"),
      resolve(INSCYD_RAW_DIR, "Power_Performance_Decoder___V3.zwo"),
    ]);

    await Promise.all([
      page.waitForResponse((resp) => resp.url().includes("/api/submit") && resp.status() === 201),
      page.locator("#upload-form button[type='submit']").click(),
    ]);

    await page.waitForURL("**/dashboard");
    await navigateAndWait(page, "/dashboard?tab=reports");

    const reportRow = page.locator(".job-row").filter({ hasText: "2026-04-04" }).first();
    await expect(reportRow).toBeVisible();
    await expect(reportRow.getByText("INSCYD", { exact: true })).toBeVisible();

    await Promise.all([
      page.waitForResponse((resp) => resp.url().includes("/api/jobs/") && resp.url().includes("/trigger") && resp.status() === 200),
      reportRow.getByRole("button", { name: "분석 시작" }).click(),
    ]);

    let reportLinkVisible = false;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await navigateAndWait(page, "/dashboard?tab=reports");
      const refreshedRow = page.locator(".job-row").filter({ hasText: "2026-04-04" }).first();
      if (await refreshedRow.getByRole("link", { name: "리포트" }).isVisible().catch(() => false)) {
        reportLinkVisible = true;
        break;
      }
      await page.waitForTimeout(1000);
    }

    expect(reportLinkVisible).toBeTruthy();

    await page.locator(".job-row").filter({ hasText: "2026-04-04" }).first().getByRole("link", { name: "리포트" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("text=INSCYD Interpretation")).toBeVisible();
    await expect(page.locator("text=INSCYD가 제시한 핵심 지표")).toBeVisible();
    await expect(page.locator("text=원본 PDF 열기")).toBeVisible();
  });
});
