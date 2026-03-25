/**
 * tests/e2e/server-user-auth.spec.ts
 *
 * Playwright E2E tests for the server/ HTMX stack user features.
 *
 * Covers:
 *   1. Google OAuth login flow (route interception mock)
 *   2. Profile page — load, body composition fields, trends table
 *   3. Dashboard My Reports filter — tab toggle
 *   4. Unauthenticated access — /profile redirect
 *   5. Navigation — login/logout UI differences
 *
 * Prerequisites:
 *   - Test server running via `python tests/e2e/run_test_server.py`
 *   - Test session cookie available in .test-session-cookie
 */

import { expect, test } from "@playwright/test";

import { loginAsTestUser, logout, navigateAndWait } from "./helpers";

// ── 1. Google OAuth Login Flow ─────────────────────────────────────

test.describe("Google OAuth login flow", () => {
  test("GET /auth/google/login redirects to Google consent screen", async ({
    page,
  }) => {
    // Intercept the redirect to Google to avoid hitting real Google servers
    let redirectUrl = "";
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("accounts.google.com")) {
        redirectUrl = url;
      }
    });

    const response = await page.goto("/auth/google/login", {
      waitUntil: "commit",
    });

    // Should attempt redirect to Google (302 → Google OAuth URL)
    // Since Google is not available, verify the redirect was attempted
    const finalUrl = page.url();
    const isGoogleRedirect =
      finalUrl.includes("accounts.google.com") ||
      redirectUrl.includes("accounts.google.com");

    expect(isGoogleRedirect).toBeTruthy();
  });

  test("GET /auth/logout clears session and redirects to landing", async ({
    context,
    page,
  }) => {
    // First log in
    await loginAsTestUser(context);

    // Visit a page to confirm we are logged in
    await navigateAndWait(page, "/");
    await expect(page.locator("text=E2E Test User")).toBeVisible();

    // Logout
    await page.goto("/auth/logout", { waitUntil: "networkidle" });

    // Should be on landing page
    expect(page.url()).toContain("/");

    // Should see login button, not user info
    await expect(page.locator('a[href="/auth/google/login"]')).toBeVisible();
    await expect(page.locator("text=E2E Test User")).not.toBeVisible();
  });
});

// ── 2. Profile Page ────────────────────────────────────────────────

test.describe("Profile page", () => {
  test.beforeEach(async ({ context }) => {
    await loginAsTestUser(context);
  });

  test("loads and displays user info", async ({ page }) => {
    await navigateAndWait(page, "/profile");

    // Page title
    await expect(page.locator("h1")).toContainText("프로필");

    // User card shows display name and email
    await expect(
      page.locator("h2", { hasText: "E2E Test User" }),
    ).toBeVisible();
    await expect(page.locator("text=e2e-test@example.com")).toBeVisible();

    // Avatar image is rendered in the profile card (main area, not nav)
    const avatar = page.locator("main img.rounded-full");
    await expect(avatar).toBeVisible();
    await expect(avatar).toHaveAttribute("src", /e2e-avatar/);
  });

  test("displays body composition fields with seeded values", async ({
    page,
  }) => {
    await navigateAndWait(page, "/profile");

    // Body composition section exists
    await expect(page.locator("text=체성분")).toBeVisible();

    // Verify body composition fields exist and have numeric values
    const weightInput = page.locator('input[name="weight_kg"]');
    const weightVal = await weightInput.inputValue();
    expect(parseFloat(weightVal)).toBeGreaterThan(0);

    const heightInput = page.locator('input[name="height_cm"]');
    await expect(heightInput).toHaveValue("175.0");

    const bodyFatInput = page.locator('input[name="body_fat_pct"]');
    await expect(bodyFatInput).toHaveValue("15.0");

    const smmInput = page.locator('input[name="skeletal_muscle_mass"]');
    await expect(smmInput).toHaveValue("33.0");

    const bmiInput = page.locator('input[name="bmi"]');
    await expect(bmiInput).toHaveValue("23.7");
  });

  test("displays basic info fields with seeded values", async ({ page }) => {
    await navigateAndWait(page, "/profile");

    // Basic info section
    await expect(page.locator("text=기본 정보")).toBeVisible();

    // Birth year
    const birthYear = page.locator('input[name="birth_year"]');
    await expect(birthYear).toHaveValue("1990");

    // Gender select
    const gender = page.locator('select[name="gender"]');
    await expect(gender).toHaveValue("male");

    // Training level select
    const trainingLevel = page.locator('select[name="training_level"]');
    await expect(trainingLevel).toHaveValue("advanced");
  });

  test("body composition inline edit saves via HTMX", async ({ page }) => {
    await navigateAndWait(page, "/profile");

    // Change weight
    const weightInput = page.locator('input[name="weight_kg"]');
    await weightInput.fill("74.0");
    await weightInput.dispatchEvent("change");

    // Wait for HTMX response — the #body-comp-fields div should be swapped
    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/profile") && resp.status() === 200,
    );

    // Verify the new value persisted (page re-renders the partial)
    const updatedWeight = page.locator('input[name="weight_kg"]');
    await expect(updatedWeight).toHaveValue("74.0");

    // Reload to confirm persistence
    await navigateAndWait(page, "/profile");
    const reloadedWeight = page.locator('input[name="weight_kg"]');
    await expect(reloadedWeight).toHaveValue("74.0");

    // Restore original value for test idempotency
    const restoreInput = page.locator('input[name="weight_kg"]');
    await restoreInput.fill("72.5");
    await restoreInput.dispatchEvent("change");
    await page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/profile") && resp.status() === 200,
    );
  });

  test("displays fitness trends section", async ({ page }) => {
    await navigateAndWait(page, "/profile");

    // Trends section exists
    await expect(
      page.locator("text=피트니스 지표 트렌드"),
    ).toBeVisible();

    // Since no test submissions exist yet, expect empty message
    await expect(
      page.locator("#fitness-trends"),
    ).toBeVisible();
  });

  test("measured_at date field is displayed", async ({ page }) => {
    await navigateAndWait(page, "/profile");

    // Measured at date field
    const measuredAt = page.locator('input[name="measured_at"]');
    await expect(measuredAt).toHaveValue("2026-03-20");
  });
});

// ── 3. Dashboard My Reports Filter ─────────────────────────────────

test.describe("Dashboard My Reports filter", () => {
  test("logged-in user sees filter tabs", async ({ context, page }) => {
    await loginAsTestUser(context);
    await navigateAndWait(page, "/dashboard");

    // Filter tabs container is visible
    const filterTabs = page.locator("#filter-tabs");
    await expect(filterTabs).toBeVisible();

    // Both tabs are present
    await expect(
      filterTabs.locator('button[data-filter="all"]'),
    ).toBeVisible();
    await expect(
      filterTabs.locator('button[data-filter="mine"]'),
    ).toBeVisible();

    // "All" tab text
    await expect(filterTabs.locator("text=All")).toBeVisible();
    // "My Reports" tab text
    await expect(filterTabs.locator("text=My Reports")).toBeVisible();
  });

  test("clicking My Reports tab triggers HTMX request", async ({
    context,
    page,
  }) => {
    await loginAsTestUser(context);
    await navigateAndWait(page, "/dashboard");

    // Click "My Reports" tab
    const myReportsBtn = page.locator('button[data-filter="mine"]');

    // Wait for the HTMX request to complete
    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/jobs/partial?filter=mine") &&
        resp.status() === 200,
    );

    await myReportsBtn.click();
    await responsePromise;

    // "My Reports" tab should now be active (has bg-gray-900)
    await expect(myReportsBtn).toHaveClass(/bg-gray-900/);

    // "All" tab should be inactive
    const allBtn = page.locator('button[data-filter="all"]');
    await expect(allBtn).toHaveClass(/bg-gray-100/);
  });

  test("switching back to All tab works", async ({ context, page }) => {
    await loginAsTestUser(context);
    await navigateAndWait(page, "/dashboard");

    // Click "My Reports" first
    const myReportsBtn = page.locator('button[data-filter="mine"]');
    await myReportsBtn.click();
    await page.waitForResponse((resp) =>
      resp.url().includes("/api/jobs/partial?filter=mine"),
    );

    // Click "All" to switch back
    const allBtn = page.locator('button[data-filter="all"]');
    const responsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/jobs/partial") &&
        !resp.url().includes("filter=mine") &&
        resp.status() === 200,
    );

    await allBtn.click();
    await responsePromise;

    // "All" tab should be active
    await expect(allBtn).toHaveClass(/bg-gray-900/);
  });

  test("anonymous user does NOT see filter tabs", async ({ page }) => {
    await navigateAndWait(page, "/dashboard");

    // Filter tabs should not be present
    await expect(page.locator("#filter-tabs")).not.toBeVisible();
    await expect(page.locator("text=My Reports")).not.toBeVisible();
  });
});

// ── 4. Unauthenticated Access ──────────────────────────────────────

test.describe("Unauthenticated access", () => {
  test("/profile redirects to Google login", async ({ page }) => {
    // Visit /profile without being logged in
    const response = await page.goto("/profile", {
      waitUntil: "commit",
    });

    // Should redirect — final URL should contain auth/google/login or accounts.google
    const finalUrl = page.url();
    expect(
      finalUrl.includes("/auth/google/login") ||
        finalUrl.includes("accounts.google.com"),
    ).toBeTruthy();
  });

  test("PATCH /api/profile returns 401 without session", async ({
    request,
  }) => {
    const response = await request.patch("/api/profile", {
      form: { weight_kg: "80.0" },
    });
    expect(response.status()).toBe(401);
  });

  test("GET /api/profile/trends returns 401 without session", async ({
    request,
  }) => {
    const response = await request.get("/api/profile/trends");
    expect(response.status()).toBe(401);
  });
});

// ── 5. Navigation Auth State ───────────────────────────────────────

test.describe("Navigation — login/logout UI", () => {
  test("anonymous visitor sees login button, not profile link", async ({
    page,
  }) => {
    await navigateAndWait(page, "/");

    // Login link visible
    const loginLink = page.locator('a[href="/auth/google/login"]');
    await expect(loginLink).toBeVisible();
    await expect(loginLink).toContainText("로그인");

    // Profile link NOT visible
    await expect(page.locator('a[href="/profile"]')).not.toBeVisible();

    // Logout text NOT visible
    await expect(page.locator("text=로그아웃")).not.toBeVisible();
  });

  test("logged-in user sees profile link and display name", async ({
    context,
    page,
  }) => {
    await loginAsTestUser(context);
    await navigateAndWait(page, "/");

    // Display name visible in nav
    await expect(page.locator("text=E2E Test User")).toBeVisible();

    // Profile link visible
    const profileLink = page.locator('a[href="/profile"]');
    await expect(profileLink).toBeVisible();
    await expect(profileLink).toContainText("프로필");

    // Logout link visible
    const logoutLink = page.locator('a[href="/auth/logout"]');
    await expect(logoutLink).toBeVisible();
    await expect(logoutLink).toContainText("로그아웃");

    // Login link NOT visible
    await expect(
      page.locator('a[href="/auth/google/login"]'),
    ).not.toBeVisible();
  });

  test("logged-in user avatar is rendered in nav", async ({
    context,
    page,
  }) => {
    await loginAsTestUser(context);
    await navigateAndWait(page, "/");

    // Avatar image in nav bar
    const navAvatar = page.locator("nav img.rounded-full");
    await expect(navAvatar).toBeVisible();
    await expect(navAvatar).toHaveAttribute("src", /e2e-avatar/);
  });

  test("navigation highlights active page", async ({ context, page }) => {
    await loginAsTestUser(context);

    // Dashboard page — dashboard link should be highlighted
    await navigateAndWait(page, "/dashboard");
    const dashLink = page.locator('nav a[href="/dashboard"]');
    await expect(dashLink).toHaveClass(/bg-gray-900 text-white/);

    // Profile page — profile link should be highlighted
    await navigateAndWait(page, "/profile");
    const profileLink = page.locator('nav a[href="/profile"]');
    await expect(profileLink).toHaveClass(/bg-gray-900 text-white/);
  });

  test("profile link appears on all pages when logged in", async ({
    context,
    page,
  }) => {
    await loginAsTestUser(context);

    // Check landing page
    await navigateAndWait(page, "/");
    await expect(page.locator('a[href="/profile"]')).toBeVisible();

    // Check dashboard
    await navigateAndWait(page, "/dashboard");
    await expect(page.locator('a[href="/profile"]')).toBeVisible();

    // Check upload page
    await navigateAndWait(page, "/upload");
    await expect(page.locator('a[href="/profile"]')).toBeVisible();
  });

  test("profile link hidden on all pages when anonymous", async ({
    page,
  }) => {
    // Check landing page
    await navigateAndWait(page, "/");
    await expect(page.locator('a[href="/profile"]')).not.toBeVisible();

    // Check dashboard
    await navigateAndWait(page, "/dashboard");
    await expect(page.locator('a[href="/profile"]')).not.toBeVisible();

    // Check upload page
    await navigateAndWait(page, "/upload");
    await expect(page.locator('a[href="/profile"]')).not.toBeVisible();
  });
});
