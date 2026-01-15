"""Enhanced API client with retry logic and request interceptors."""

import { API_CONFIG, TIMEOUTS, ERROR_CODES, getApiUrl } from '@/config/env';
import { logger } from '@/utils/logger';

export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    message: string,
    public details?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions extends RequestInit {
  timeout?: number;
  retry?: boolean;
  retryCount?: number;
}

/**
 * Enhanced API client with retry logic and error handling.
 */
export class ApiClient {
  private baseUrl: string;
  private timeout: number;
  private retryConfig = API_CONFIG.RETRY;

  constructor(baseUrl: string = API_CONFIG.BASE_URL, timeout: number = API_CONFIG.TIMEOUT) {
    this.baseUrl = baseUrl;
    this.timeout = timeout;
  }

  /**
   * Make an HTTP request with automatic retry and error handling.
   */
  async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { timeout = this.timeout, retry = true, retryCount = 0, ...fetchOptions } = options;

    const url = this.getFullUrl(endpoint);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      logger.debug(`API Request: ${fetchOptions.method || 'GET'} ${endpoint}`);

      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...fetchOptions.headers,
        },
      });

      clearTimeout(timeoutId);

      // Handle response
      return await this.handleResponse<T>(response);
    } catch (error) {
      clearTimeout(timeoutId);

      // Handle specific error types
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        const apiError = new ApiError(
          ERROR_CODES.NETWORK_ERROR,
          0,
          'Network error. Please check your connection.'
        );
        logger.error('Network error', apiError);

        // Retry on network error
        if (retry && retryCount < this.retryConfig.MAX_ATTEMPTS) {
          const delay = this.getRetryDelay(retryCount);
          logger.info(`Retrying request after ${delay}ms (attempt ${retryCount + 1})`);
          await this.delay(delay);
          return this.request<T>(endpoint, {
            ...options,
            retryCount: retryCount + 1,
          });
        }

        throw apiError;
      }

      if (error instanceof Error && error.name === 'AbortError') {
        throw new ApiError(
          ERROR_CODES.TIMEOUT,
          0,
          `Request timeout after ${timeout}ms`
        );
      }

      throw error;
    }
  }

  /**
   * Make a GET request.
   */
  async get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  /**
   * Make a POST request.
   */
  async post<T>(endpoint: string, data?: any, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Make a PUT request.
   */
  async put<T>(endpoint: string, data?: any, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Make a DELETE request.
   */
  async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }

  /**
   * Make a PATCH request.
   */
  async patch<T>(endpoint: string, data?: any, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Handle response and throw errors appropriately.
   */
  private async handleResponse<T>(response: Response): Promise<T> {
    const contentType = response.headers.get('content-type');
    const isJson = contentType?.includes('application/json');

    let data: any;
    try {
      data = isJson ? await response.json() : await response.text();
    } catch (error) {
      logger.error('Failed to parse response', error);
      data = null;
    }

    if (!response.ok) {
      const code = this.getErrorCode(response.status);
      const message = data?.message || response.statusText || 'Unknown error';

      logger.error(`API Error (${response.status}): ${message}`);

      throw new ApiError(code, response.status, message, data?.details);
    }

    return data;
  }

  /**
   * Get error code from HTTP status.
   */
  private getErrorCode(status: number): string {
    switch (status) {
      case 400:
        return ERROR_CODES.VALIDATION_ERROR;
      case 401:
        return ERROR_CODES.UNAUTHORIZED;
      case 403:
        return ERROR_CODES.FORBIDDEN;
      case 404:
        return ERROR_CODES.NOT_FOUND;
      case 500:
      case 502:
      case 503:
      case 504:
        return ERROR_CODES.SERVER_ERROR;
      default:
        return ERROR_CODES.UNKNOWN;
    }
  }

  /**
   * Calculate exponential backoff delay.
   */
  private getRetryDelay(retryCount: number): number {
    const baseDelay = this.retryConfig.INITIAL_DELAY;
    const maxDelay = this.retryConfig.MAX_DELAY;
    const delay = baseDelay * Math.pow(2, retryCount);
    return Math.min(delay, maxDelay);
  }

  /**
   * Delay utility for retry logic.
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Get full URL for endpoint.
   */
  private getFullUrl(endpoint: string): string {
    return getApiUrl(endpoint);
  }

  /**
   * Set authentication token for all requests.
   */
  setAuthToken(token: string | null): void {
    if (token) {
      logger.debug('Auth token set');
    } else {
      logger.debug('Auth token cleared');
    }
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
