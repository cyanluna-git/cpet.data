/**
 * Navigation 타입 및 상수
 * 라우팅 관련 타입 정의
 */

/**
 * 가능한 모든 뷰/페이지
 */
export const ROUTE_VIEWS = {
  // Researcher routes
  RESEARCHER_DASHBOARD: 'researcher-dashboard',
  SUBJECT_LIST: 'subject-list',
  SUBJECT_DETAIL: 'subject-detail',
  COHORT_ANALYSIS: 'cohort-analysis',

  // Subject routes
  SUBJECT_DASHBOARD: 'subject-dashboard',

  // Shared routes
  TEST_VIEW: 'test-view',
  METABOLISM: 'metabolism',
} as const;

export type View = typeof ROUTE_VIEWS[keyof typeof ROUTE_VIEWS];

/**
 * Navigation 파라미터
 */
export interface NavigationParams {
  testId?: string;
  subjectId?: string;
}
