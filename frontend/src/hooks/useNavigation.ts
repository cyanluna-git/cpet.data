/**
 * useNavigation 커스텀 훅
 * 일관된 네비게이션 로직 제공
 */

import { useNavigate } from 'react-router-dom';
import type { View, NavigationParams } from '@/types/navigation';
import { getNavigationPath } from '@/utils/navigationConfig';

/**
 * useNavigation 훅
 * 모든 페이지에서 동일한 네비게이션 로직 사용
 *
 * @example
 * const { handleNavigate, handleLogout } = useNavigation();
 * <Button onClick={() => handleNavigate('cohort-analysis')}>
 *   코호트 분석
 * </Button>
 */
export function useNavigation() {
  const navigate = useNavigate();

  const handleNavigate = (view: View, params?: NavigationParams) => {
    const path = getNavigationPath(view, params);
    navigate(path);
  };

  return { handleNavigate };
}
