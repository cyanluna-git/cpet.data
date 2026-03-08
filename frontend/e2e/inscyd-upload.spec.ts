import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { loginAsAdmin, loginAsSubjectUser, resetAuthState } from './helpers/auth';

const pdfPath = path.resolve(process.cwd(), '../inscyd/INSCYD_KY Park_2026.pdf.pdf');
const pdfBuffer = readFileSync(pdfPath);

async function uploadInscydReport(page: Page, filename: string) {
  await page.goto('/admin/data');
  await expect(page.getByRole('heading', { name: 'DB 관리' })).toBeVisible();

  await page.getByRole('button', { name: '테스트 업로드' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType: 'application/pdf',
    buffer: pdfBuffer,
  });

  await expect(page.getByText(filename)).toBeVisible();
  await page.getByRole('button', { name: '업로드' }).click();

  await expect(page.getByText('업로드 완료')).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('dialog').getByText('Geunyun Park', { exact: true })).toBeVisible();
  await expect(page.getByText('파싱 성공')).toBeVisible();

  await page.getByRole('dialog').getByRole('button', { name: '확인' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
}

async function uploadOwnInscydReportFromDashboard(page: Page, filename: string) {
  await page.goto('/my-dashboard');
  await expect(page.getByRole('heading', { name: '내 대사 프로파일' })).toBeVisible();

  await page.getByRole('button', { name: 'INSCYD 리포트 업로드' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'INSCYD 리포트 업로드' })).toBeVisible();
  await expect(page.getByText('INSCYD PDF(.pdf)만 업로드할 수 있습니다')).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType: 'application/pdf',
    buffer: pdfBuffer,
  });

  await expect(page.getByText(filename)).toBeVisible();
  await page.getByRole('button', { name: '업로드' }).click();

  await expect(page.getByText('업로드 완료')).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('dialog').getByText('Geunyun Park', { exact: true })).toBeVisible();
  await expect(page.getByText('파싱 성공')).toBeVisible();

  await page.getByRole('dialog').getByRole('button', { name: '확인' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
}

test.describe('INSCYD Local Upload Flow', () => {
  test.describe.configure({ mode: 'serial' });

  test('admin upload is reflected in subject detail and subject dashboard', async ({ page, browserName, request }) => {
    test.skip(browserName !== 'chromium', 'Mutates shared local DB; run once on chromium only.');

    await loginAsAdmin(page);

    await uploadInscydReport(page, 'INSCYD_KY Park_2026_local-e2e-a.pdf');
    await uploadInscydReport(page, 'INSCYD_KY Park_2026_local-e2e-b.pdf');

    await page.goto('/subjects');
    await page.getByPlaceholder('피험자 ID, 이름, 훈련 수준으로 검색...').fill('SUB-PAR-GEU');

    const subjectRow = page.locator('tbody tr', { hasText: 'SUB-PAR-GEU' }).first();
    await expect(subjectRow).toContainText('Geunyun Park');
    await subjectRow.locator('button[title="상세 보기"]').click();

    await page.waitForURL(/\/subjects\/[^/]+$/);
    await expect(page.getByText('최신 INSCYD 요약')).toBeVisible();
    await expect(page.getByText('INSCYD 리포트 추이')).toBeVisible();
    await page.getByRole('tab', { name: 'Test History' }).click();
    await expect(page.getByText('INSCYD 리포트 히스토리')).toBeVisible();
    await expect(page.getByText('51.7').first()).toBeVisible();
    await expect(page.getByText('150').first()).toBeVisible();

    await resetAuthState(page);
    const loginResponse = await request.post('http://localhost:8100/api/auth/login', {
      form: {
        username: 'geunyun.park@cpet.com',
        password: 'cpet2026!',
      },
    });
    expect(loginResponse.ok()).toBeTruthy();
    const { access_token } = await loginResponse.json();
    await page.goto('/login');
    await page.evaluate((token: string) => {
      localStorage.setItem('access_token', token);
    }, access_token);
    await page.goto('/my-dashboard');
    await expect(page.getByRole('navigation')).toBeVisible();
    await expect(page.getByText('최신 INSCYD 리포트')).toBeVisible();
    await expect(page.getByText('INSCYD 변화 추이')).toBeVisible();
    await expect(page.getByText('정기적으로 받은 INSCYD 리포트의 주요 지표 변화를 확인하세요')).toBeVisible();
    await expect(page.getByText('51.7').first()).toBeVisible();
    await expect(page.getByText('150').first()).toBeVisible();
  });

  test('subject can upload own INSCYD report from my dashboard', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Mutates shared local DB; run once on chromium only.');

    await loginAsSubjectUser(page, 'geunyun.park@cpet.com', 'cpet2026!');
    await uploadOwnInscydReportFromDashboard(page, 'INSCYD_KY Park_2026_subject-self-upload.pdf');

    await page.goto('/my-dashboard');
    await expect(page.getByText('최신 INSCYD 리포트')).toBeVisible();
    await expect(page.getByText('INSCYD 변화 추이')).toBeVisible();
    await expect(page.getByText('51.7').first()).toBeVisible();
    await expect(page.getByText('150').first()).toBeVisible();
  });
});
