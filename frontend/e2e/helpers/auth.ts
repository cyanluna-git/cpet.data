import type { Page } from '@playwright/test';

export async function demoLoginAsResearcher(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: '연구자 데모' }).click();
  await page.getByRole('navigation').waitFor({ state: 'visible', timeout: 10000 });
}

export async function demoLoginAsSubject(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: '피험자 데모' }).click();
  await page.getByRole('navigation').waitFor({ state: 'visible', timeout: 10000 });
}

export async function loginWithCredentials(
  page: Page,
  email: string,
  password: string,
) {
  await page.goto('/login');
  await page.getByLabel('이메일').fill(email);
  await page.getByLabel('비밀번호').fill(password);
  await page.getByRole('button', { name: '로그인' }).click();
  await page.getByRole('navigation').waitFor({ state: 'visible', timeout: 15000 });
}

export async function loginAsAdmin(page: Page) {
  await loginWithCredentials(page, 'gerald.park@cpet.com', 'cpet2026!');
}

export async function loginAsSubjectUser(
  page: Page,
  email: string,
  password: string,
) {
  await loginWithCredentials(page, email, password);
}

export async function resetAuthState(page: Page) {
  await page.goto('/');
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.context().clearCookies();
}
