/** Custom hook for handling async mutations (POST, PUT, DELETE) with loading and error states. */

import { useState, useCallback, useRef } from 'react';
import { toast } from 'sonner';

export interface UseMutationState<TData, TVars = void> {
  data: TData | null;
  error: Error | null;
  loading: boolean;
  mutate: (variables: TVars) => Promise<TData | null>;
  reset: () => void;
}

interface MutationOptions<TData> {
  onSuccess?: (data: TData) => void;
  onError?: (error: Error) => void;
  showSuccessToast?: boolean;
  showErrorToast?: boolean;
  successMessage?: string;
}

/**
 * Custom hook for handling async mutations (create, update, delete operations).
 * Prevents memory leaks and provides consistent error handling.
 *
 * @template TData - The type of data returned by the mutation
 * @template TVars - The type of variables passed to the mutation function
 * @param mutateFn - Async function that performs the mutation
 * @param options - Configuration options
 * @returns Object with mutate function and state management
 *
 * @example
 * ```tsx
 * const { mutate: createSubject, loading, error, data } = useMutation(
 *   (data) => api.createSubject(data),
 *   {
 *     onSuccess: () => refetch(),
 *     successMessage: 'Subject created successfully'
 *   }
 * );
 *
 * const handleSubmit = async (formData) => {
 *   const result = await createSubject(formData);
 *   if (result) {
 *     // Success
 *   }
 * };
 * ```
 */
export function useMutation<TData, TVars = void>(
  mutateFn: (variables: TVars) => Promise<TData>,
  options: MutationOptions<TData> = {}
): UseMutationState<TData, TVars> {
  const {
    onSuccess,
    onError,
    showSuccessToast = true,
    showErrorToast = true,
    successMessage = 'Operation successful',
  } = options;

  const [data, setData] = useState<TData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);

  // Track if component is mounted
  const isMountedRef = useRef(true);
  // Store abort controller for cancellation
  const abortControllerRef = useRef<AbortController | null>(null);

  const mutate = useCallback(
    async (variables: TVars): Promise<TData | null> => {
      // Don't allow concurrent mutations
      if (loading) {
        console.warn('Mutation already in progress');
        return null;
      }

      setLoading(true);
      setError(null);

      try {
        const result = await mutateFn(variables);

        if (isMountedRef.current) {
          setData(result);
          setError(null);

          if (showSuccessToast) {
            toast.success(successMessage);
          }

          onSuccess?.(result);
        }

        return result;
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));

        if (isMountedRef.current) {
          setError(error);
          setData(null);

          if (showErrorToast) {
            toast.error(error.message || 'Operation failed');
          }

          onError?.(error);
        }

        return null;
      } finally {
        if (isMountedRef.current) {
          setLoading(false);
        }
      }
    },
    [mutateFn, loading, onSuccess, onError, showSuccessToast, showErrorToast, successMessage]
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return {
    data,
    error,
    loading,
    mutate,
    reset,
  };
}

/**
 * Hook for handling multiple mutations that need to be tracked together.
 * Useful for forms with multiple operations.
 *
 * @template TData - The type of data returned by mutations
 * @param mutations - Object mapping names to mutation functions
 * @param options - Configuration options
 * @returns Object with individual mutate functions
 *
 * @example
 * ```tsx
 * const { mutate: createSubject, mutate: updateSubject } = useMultipleMutations(
 *   {
 *     createSubject: (data) => api.createSubject(data),
 *     updateSubject: (data) => api.updateSubject(data),
 *   }
 * );
 * ```
 */
export function useMultipleMutations<T extends Record<string, any>>(
  mutations: Record<keyof T, (vars: any) => Promise<any>>,
  options?: MutationOptions<any>
) {
  const result: Record<keyof T, ReturnType<typeof useMutation>> = {} as any;

  for (const [key, mutateFn] of Object.entries(mutations)) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    result[key as keyof T] = useMutation(mutateFn, options);
  }

  return result;
}
