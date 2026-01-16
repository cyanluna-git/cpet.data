import { test, expect } from '@playwright/test';
import { demoLoginAsResearcher } from './helpers/auth';

test.describe('Authentication Flow', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/');
    await page.waitForURL('**/login');
    expect(page.url()).toContain('login');
  });

  test('should login with valid credentials', async ({ page }) => {
    await demoLoginAsResearcher(page);
    expect(page.url()).not.toContain('/login');
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'wrong@example.com');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    
    // Error is shown via toast (sonner)
    const toast = page.locator('[data-sonner-toast]');
    await expect(toast.first()).toBeVisible({ timeout: 5000 });
  });

  test('should logout successfully', async ({ page }) => {
    await demoLoginAsResearcher(page);

    // Logout is in the user dropdown
    await page.getByRole('button', { name: /연구자 데모/ }).click();
    await page.getByRole('menuitem', { name: '로그아웃' }).click();
    await page.waitForURL('**/login');
    expect(page.url()).toContain('login');
  });

  test('should display login form with all required fields', async ({ page }) => {
    await page.goto('/login');
    
    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    const submitButton = page.locator('button[type="submit"]');
    
    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(submitButton).toBeVisible();
  });
});
