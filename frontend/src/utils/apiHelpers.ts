/**
 * API 응답 헬퍼 함수
 * PaginatedResponse 처리를 단순화
 */

import { api } from './api';

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * API 응답에서 아이템 배열을 추출
 * PaginatedResponse 또는 배열 형식 모두 처리
 *
 * @param response - API 응답 (배열 또는 PaginatedResponse)
 * @returns 아이템 배열
 *
 * @example
 * const response = await api.getSubjects();
 * const subjects = extractItems(response);
 */
export function extractItems<T>(
  response: T[] | PaginatedResponse<T> | any
): T[] {
  // 배열 형식
  if (Array.isArray(response)) {
    return response;
  }

  // PaginatedResponse 형식
  if (response?.items && Array.isArray(response.items)) {
    return response.items;
  }

  // 단일 항목 형식
  if (response?.data && Array.isArray(response.data)) {
    return response.data;
  }

  console.warn('Unable to extract items from response:', response);
  return [];
}

/**
 * PaginatedResponse 정보 추출
 * @param response - API 응답
 * @returns 페이지 정보 { total, page, page_size, total_pages }
 */
export function extractPaginationInfo(response: any) {
  return {
    total: response?.total || 0,
    page: response?.page || 1,
    page_size: response?.page_size || 20,
    total_pages: response?.total_pages || 1,
  };
}

/**
 * API 오류 메시지 추출
 * @param error - 에러 객체
 * @returns 사용자 친화적 에러 메시지
 */
export function getErrorMessage(error: any): string {
  if (error?.response?.data?.message) {
    return error.response.data.message;
  }

  if (error?.message) {
    return error.message;
  }

  if (error?.detail) {
    return error.detail;
  }

  return '요청 처리 중 오류가 발생했습니다';
}
