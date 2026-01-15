/**
 * Navigation 설정
 * 뷰/페이지에서 실제 라우트 경로로의 매핑
 */

import type { View } from '@/types/navigation';

/**
 * View 타입에서 URL 경로로의 매핑
 * 각 뷰를 어떤 경로로 네비게이트할지 정의
 */
export const navigationConfig: Record<
  View,
  (params?: { testId?: string; subjectId?: string }) => string
> = {
  'researcher-dashboard': () => '/',
  'subject-dashboard': () => '/my-dashboard',
  'subject-list': () => '/subjects',
  'subject-detail': (params) => `/subjects/${params?.subjectId}`,
  'cohort-analysis': () => '/cohort',
  'metabolism': () => '/metabolism',
  'test-view': (params) => `/tests/${params?.testId}`,
};

/**
 * Navigation 경로를 생성하는 헬퍼 함수
 * @param view - 이동할 뷰
 * @param params - 동적 파라미터
 * @returns 이동할 경로
 */
export function getNavigationPath(
  view: View,
  params?: { testId?: string; subjectId?: string }
): string {
  const pathFn = navigationConfig[view];
  if (!pathFn) {
    console.warn(`Unknown navigation view: ${view}`);
    return '/';
  }
  return pathFn(params);
}
