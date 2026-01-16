/** Custom hook for handling async data fetching with automatic cleanup and cancellation. */

import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from 'sonner';

export interface UseFetchState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refetch: () => Promise<void>;
}

interface FetchOptions {
  onSuccess?: (data: any) => void;
  onError?: (error: Error) => void;
  autoFetch?: boolean;
  showErrorToast?: boolean;
}

/**
 * Custom hook for handling async data fetching with built-in cancellation support.
 * Prevents memory leaks and race conditions in React.
 *
 * @template T - The type of data returned by the fetch function
 * @param fetchFn - Async function that returns data
 * @param options - Configuration options
 * @returns Object with data, error, loading state and refetch function
 *
 * @example
 * ```tsx
 * const { data: subjects, loading, error, refetch } = useFetch(
 *   () => api.getSubjects(),
 *   { onSuccess: (data) => console.log('Loaded:', data) }
 * );
 *
 * if (loading) return <div>Loading...</div>;
 * if (error) return <div>Error: {error.message}</div>;
 * return <div>{subjects?.length || 0} subjects</div>;
 * ```
 */
export function useFetch<T>(
  fetchFn: () => Promise<T>,
  options: FetchOptions = {}
): UseFetchState<T> {
  const {
    onSuccess,
    onError,
    autoFetch = true,
    showErrorToast = true,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);

  // Track if component is mounted to prevent memory leaks
  const isMountedRef = useRef(true);
  // Store the current fetch promise for cancellation
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetch = useCallback(async () => {
    // Cancel any previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Create new abort controller for this request
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError(null);

    try {
      const result = await fetchFn();

      // Only update state if component is still mounted and request wasn't aborted
      if (isMountedRef.current && !abortControllerRef.current?.signal.aborted) {
        setData(result);
        setError(null);
        onSuccess?.(result);
      }
    } catch (err) {
      // Ignore abort errors
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const error = err instanceof Error ? err : new Error(String(err));

      if (isMountedRef.current) {
        setError(error);
        setData(null);
        onError?.(error);

        if (showErrorToast) {
          toast.error(error.message || 'Failed to fetch data');
        }
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [fetchFn, onSuccess, onError, showErrorToast]);

  // Cleanup function
  useEffect(() => {
    return () => {
      // Mark component as unmounted
      isMountedRef.current = false;
      // Cancel any pending requests
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Auto-fetch on mount or when fetchFn changes
  useEffect(() => {
    if (autoFetch) {
      isMountedRef.current = true;
      fetch();
    }
  }, [fetch, autoFetch]);

  return {
    data,
    error,
    loading,
    refetch: fetch,
  };
}

/**
 * Type-safe variant of useFetch that requires a non-null initial value.
 * Useful when you have default data.
 *
 * @template T - The type of data
 * @param initialData - Default data when fetch is in progress
 * @param fetchFn - Async function to fetch data
 * @param options - Configuration options
 * @returns Object with guaranteed non-null data
 */
export function useFetchWithDefault<T>(
  initialData: T,
  fetchFn: () => Promise<T>,
  options?: FetchOptions
) {
  const { data, ...rest } = useFetch(fetchFn, options);
  return {
    data: data ?? initialData,
    ...rest,
  };
}
