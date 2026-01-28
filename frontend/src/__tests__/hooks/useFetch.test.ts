/** Unit tests for useFetch hook. */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useFetch, useFetchWithDefault } from '@/hooks/useFetch';

describe('useFetch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it('should initialize with loading state', () => {
    const fetchFn = vi.fn(() => Promise.resolve({ id: 1, name: 'Test' }));
    const { result } = renderHook(() => useFetch(fetchFn));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('should fetch data successfully', async () => {
    const testData = { id: 1, name: 'Test' };
    const fetchFn = vi.fn(() => Promise.resolve(testData));

    const { result } = renderHook(() => useFetch(fetchFn));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(testData);
    expect(result.current.error).toBeNull();
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it('should handle errors', async () => {
    const error = new Error('Fetch failed');
    const fetchFn = vi.fn(() => Promise.reject(error));

    const { result } = renderHook(() => useFetch(fetchFn, { showErrorToast: false }));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeDefined();
    expect(result.current.error?.message).toBe('Fetch failed');
  });

  it('should refetch data', async () => {
    const testData = { id: 1, name: 'Test' };
    const fetchFn = vi.fn(() => Promise.resolve(testData));

    const { result } = renderHook(() => useFetch(fetchFn));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchFn).toHaveBeenCalledTimes(1);

    // Refetch
    act(() => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it('should not fetch when autoFetch is false', async () => {
    const fetchFn = vi.fn(() => Promise.resolve({ data: 'test' }));

    const { result } = renderHook(() => useFetch(fetchFn, { autoFetch: false }));

    expect(fetchFn).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();

    // Manually trigger fetch
    act(() => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it('should call onSuccess callback', async () => {
    const testData = { id: 1, name: 'Test' };
    const onSuccess = vi.fn();
    const fetchFn = vi.fn(() => Promise.resolve(testData));

    renderHook(() => useFetch(fetchFn, { onSuccess }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(testData);
    });
  });

  it('should call onError callback on failure', async () => {
    const error = new Error('Fetch failed');
    const onError = vi.fn();
    const fetchFn = vi.fn(() => Promise.reject(error));

    renderHook(() => useFetch(fetchFn, { onError, showErrorToast: false }));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(error);
    });
  });

  it('should handle multiple refetch calls', async () => {
    // Test that multiple refetch calls work correctly
    const fetchFn = vi.fn()
      .mockResolvedValueOnce({ id: 1 })
      .mockResolvedValueOnce({ id: 2 })
      .mockResolvedValueOnce({ id: 3 });

    const { result } = renderHook(() => useFetch(fetchFn));

    // Wait for initial fetch
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual({ id: 1 });
    expect(fetchFn).toHaveBeenCalledTimes(1);

    // First refetch
    act(() => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual({ id: 2 });
    expect(fetchFn).toHaveBeenCalledTimes(2);

    // Second refetch
    act(() => {
      result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual({ id: 3 });
    expect(fetchFn).toHaveBeenCalledTimes(3);
  });
});

describe('useFetchWithDefault', () => {
  it('should return default data while loading', async () => {
    const defaultData = { id: 0, name: 'Default' };
    const fetchFn = vi.fn(() => new Promise(() => {})); // Never resolves

    const { result } = renderHook(() => useFetchWithDefault(defaultData, fetchFn));

    expect(result.current.data).toEqual(defaultData);
    expect(result.current.loading).toBe(true);
  });

  it('should return fetched data after loading', async () => {
    const defaultData = { id: 0, name: 'Default' };
    const fetchedData = { id: 1, name: 'Fetched' };
    const fetchFn = vi.fn(() => Promise.resolve(fetchedData));

    const { result } = renderHook(() => useFetchWithDefault(defaultData, fetchFn));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual(fetchedData);
  });

  it('should return default data on error', async () => {
    const defaultData = { id: 0, name: 'Default' };
    const fetchFn = vi.fn(() => Promise.reject(new Error('Failed')));

    const { result } = renderHook(() => useFetchWithDefault(defaultData, fetchFn, { showErrorToast: false }));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should return default data, not null
    expect(result.current.data).toEqual(defaultData);
  });
});
