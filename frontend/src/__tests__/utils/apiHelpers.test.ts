/** Unit tests for API helper functions. */

import { describe, it, expect } from 'vitest';
import { extractItems, extractPaginationInfo, getErrorMessage } from '@/utils/apiHelpers';

interface TestItem {
  id: string;
  name: string;
}

describe('extractItems', () => {
  it('should extract items from array response', () => {
    const items: TestItem[] = [
      { id: '1', name: 'Item 1' },
      { id: '2', name: 'Item 2' },
    ];

    const result = extractItems(items);

    expect(result).toEqual(items);
    expect(result.length).toBe(2);
  });

  it('should extract items from PaginatedResponse', () => {
    const paginatedResponse = {
      items: [
        { id: '1', name: 'Item 1' },
        { id: '2', name: 'Item 2' },
      ],
      total: 2,
      page: 1,
      page_size: 20,
      pages: 1,
    };

    const result = extractItems(paginatedResponse);

    expect(result).toEqual(paginatedResponse.items);
    expect(result.length).toBe(2);
  });

  it('should handle empty array', () => {
    const result = extractItems([]);
    expect(result).toEqual([]);
    expect(result.length).toBe(0);
  });

  it('should handle empty items in paginated response', () => {
    const response = {
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      pages: 0,
    };

    const result = extractItems(response);

    expect(result).toEqual([]);
  });

  it('should return empty array for invalid response', () => {
    const result = extractItems(null);
    expect(result).toEqual([]);
  });

  it('should return empty array for non-array, non-paginated response', () => {
    const result = extractItems({ data: 'something' });
    expect(result).toEqual([]);
  });

  it('should handle response without items property', () => {
    const result = extractItems({ total: 10, page: 1 });
    expect(result).toEqual([]);
  });
});

describe('extractPaginationInfo', () => {
  it('should extract pagination info from response', () => {
    const response = {
      items: [{ id: '1' }],
      total: 42,
      page: 2,
      page_size: 20,
      total_pages: 3,
    };

    const info = extractPaginationInfo(response);

    expect(info).toEqual({
      total: 42,
      page: 2,
      page_size: 20,
      total_pages: 3,
    });
  });

  it('should return default values for array response', () => {
    const info = extractPaginationInfo([{ id: '1' }]);
    expect(info).toEqual({
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });
  });

  it('should handle first page', () => {
    const response = {
      items: [],
      total: 20,
      page: 1,
      page_size: 20,
      total_pages: 1,
    };

    const info = extractPaginationInfo(response);

    expect(info.page).toBe(1);
    expect(info.total_pages).toBe(1);
  });

  it('should handle last page', () => {
    const response = {
      items: [],
      total: 50,
      page: 3,
      page_size: 20,
      total_pages: 3,
    };

    const info = extractPaginationInfo(response);

    expect(info.page).toBe(3);
    expect(info.total_pages).toBe(3);
  });

  it('should return default values for invalid response', () => {
    expect(extractPaginationInfo(null)).toEqual({
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });
    expect(extractPaginationInfo(undefined)).toEqual({
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });
  });
});

describe('getErrorMessage', () => {
  const DEFAULT_ERROR_MESSAGE = '요청 처리 중 오류가 발생했습니다';

  it('should extract message from Error object', () => {
    const error = new Error('Something went wrong');
    const message = getErrorMessage(error);
    expect(message).toBe('Something went wrong');
  });

  it('should extract message from error object with message property', () => {
    const error = { message: 'Custom error' };
    const message = getErrorMessage(error);
    expect(message).toBe('Custom error');
  });

  it('should extract message from error object with response.data.message', () => {
    const error = {
      response: {
        data: {
          message: 'API error message',
        },
      },
    };
    const message = getErrorMessage(error);
    expect(message).toBe('API error message');
  });

  it('should extract message from error object with detail property', () => {
    const error = {
      detail: 'Validation failed',
    };
    const message = getErrorMessage(error);
    expect(message).toBe('Validation failed');
  });

  it('should return default message for error without extractable message', () => {
    const error = {
      response: {
        status: 404,
        statusText: 'Not Found',
      },
    };
    const message = getErrorMessage(error);
    // statusText is not extracted in current implementation
    expect(message).toBe(DEFAULT_ERROR_MESSAGE);
  });

  it('should return default message for string input', () => {
    const message = getErrorMessage('Error string');
    // String without message property returns default
    expect(message).toBe(DEFAULT_ERROR_MESSAGE);
  });

  it('should handle null error gracefully', () => {
    const message = getErrorMessage(null);
    expect(message).toBe(DEFAULT_ERROR_MESSAGE);
  });

  it('should handle undefined error', () => {
    const message = getErrorMessage(undefined);
    expect(message).toBe(DEFAULT_ERROR_MESSAGE);
  });

  it('should handle object without message property', () => {
    const error = { code: 'ERROR_CODE' };
    const message = getErrorMessage(error);
    expect(message).toBe(DEFAULT_ERROR_MESSAGE);
  });

  it('should return default message for deeply nested API errors without message', () => {
    const error = {
      response: {
        data: {
          error: 'validation_error',
          details: {
            field: 'email',
          },
        },
      },
    };
    const message = getErrorMessage(error);
    expect(message).toBe(DEFAULT_ERROR_MESSAGE);
  });
});
