/** Unit tests for useNavigation hook. */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useNavigation } from '@/hooks/useNavigation';
import * as reactRouter from 'react-router-dom';

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: vi.fn(),
}));

describe('useNavigation', () => {
  let mockNavigate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockNavigate = vi.fn();
    (reactRouter.useNavigate as any).mockReturnValue(mockNavigate);
  });

  it('should return handleNavigate function', () => {
    const { result } = renderHook(() => useNavigation());
    expect(result.current).toHaveProperty('handleNavigate');
    expect(typeof result.current.handleNavigate).toBe('function');
  });

  it('should navigate to researcher dashboard', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('researcher-dashboard');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('should navigate to subject dashboard', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('subject-dashboard');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/my-dashboard');
  });

  it('should navigate to subject list', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('subject-list');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/subjects');
  });

  it('should navigate to subject detail with id parameter', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('subject-detail', { id: 'test-id' });
    });

    expect(mockNavigate).toHaveBeenCalledWith('/subjects/test-id');
  });

  it('should navigate to single test view with id parameter', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('single-test-view', { id: 'test-123' });
    });

    expect(mockNavigate).toHaveBeenCalledWith('/tests/test-123');
  });

  it('should navigate to cohort analysis', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('cohort-analysis');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/cohort');
  });

  it('should navigate to metabolism page', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('metabolism');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/metabolism');
  });

  it('should navigate to login', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('login');
    });

    expect(mockNavigate).toHaveBeenCalledWith('/login');
  });

  it('should handle unknown view gracefully', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('unknown-view');
    });

    // Should navigate to home by default
    expect(mockNavigate).toHaveBeenCalled();
  });

  it('should pass through multiple parameters', () => {
    const { result } = renderHook(() => useNavigation());

    act(() => {
      result.current.handleNavigate('subject-detail', {
        id: 'subject-1',
        tab: 'tests',
        filter: 'recent',
      });
    });

    expect(mockNavigate).toHaveBeenCalled();
  });
});
