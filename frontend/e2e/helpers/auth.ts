import type { Page } from '@playwright/test';

export async function demoLoginAsResearcher(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: '연구자 데모' }).click();
  await page.getByRole('navigation').waitFor({ state: 'visible', timeout: 10000 });
}
