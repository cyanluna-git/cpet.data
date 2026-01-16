import { test, expect } from '@playwright/test';

// Admin e2e: verifies the Super Admin MVP UI works end-to-end.
// Assumes backend is reachable at http://localhost:8100 (Vite proxies /api -> backend).

test.describe('Super Admin Flow', () => {
  test('admin can login, view dashboard, manage users', async ({ page, request }) => {
    const email = `admin-e2e+${Date.now()}@example.com`;
    const password = 'password123';

    // Bootstrap an admin user (register may return 400 if already exists).
    const registerRes = await request.post('http://localhost:8100/api/auth/register', {
      data: { email, password, role: 'admin' },
    });
    expect([201, 400]).toContain(registerRes.status());

    // Go to login
    await page.goto('/login');

    await page.fill('#email', email);
    await page.fill('#password', password);
    await page.click('button[type="submit"]');

    // Login submits to / then RootRedirect should route admins to /admin
    await page.waitForURL(/\/admin(\/.*)?$/, { timeout: 15000 });

    // Dashboard
    await expect(page.getByRole('heading', { name: '슈퍼어드민' })).toBeVisible();

    // Navigate to Users page
    await page.getByRole('button', { name: /사용자 관리/ }).first().click();
    await page.waitForURL(/\/admin\/users$/, { timeout: 15000 });
    await expect(page.getByRole('heading', { name: '사용자 관리' })).toBeVisible();

    // Create a user via UI
    const createdEmail = `user-e2e+${Date.now()}@example.com`;

    await page.getByRole('button', { name: '사용자 생성' }).click();
    await expect(page.getByRole('heading', { name: /사용자 생성|사용자 수정/ })).toBeVisible();

    await page.getByPlaceholder('user@example.com').fill(createdEmail);
    await page.getByPlaceholder('******').fill('password123');

    // Select role (Radix Select)
    await page.getByRole('combobox').click();
    await page.getByRole('option', { name: 'researcher' }).click();

    await page.getByRole('button', { name: '생성' }).click();

    // Filter to find created user
    await page.getByPlaceholder('이메일로 검색...').fill(createdEmail);
    await expect(page.getByText(createdEmail)).toBeVisible({ timeout: 15000 });

    // Delete the created user
    page.once('dialog', (dialog) => dialog.accept());
    await page
      .locator('tr', { hasText: createdEmail })
      .getByRole('button', { name: '삭제' })
      .click();

    // Ensure it disappears from list
    await expect(page.getByText(createdEmail)).toHaveCount(0, { timeout: 15000 });
  });

  test('non-authenticated users are redirected from /admin to /login', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForURL('**/login');
    await expect(page).toHaveURL(/\/login$/);
  });
});
