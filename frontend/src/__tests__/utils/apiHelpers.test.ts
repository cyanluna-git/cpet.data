"""Unit tests for API helper functions."""

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
      pages: 3,
    };

    const info = extractPaginationInfo(response);

    expect(info).toEqual({
      total: 42,
      page: 2,
      page_size: 20,
      pages: 3,
      hasNextPage: true,
      hasPreviousPage: true,
    });
  });

  it('should return null for array response', () => {
    const info = extractPaginationInfo([{ id: '1' }]);
    expect(info).toBeNull();
  });

  it('should handle first page', () => {
    const response = {
      items: [],
      total: 20,
      page: 1,
      page_size: 20,
      pages: 1,
    };

    const info = extractPaginationInfo(response);

    expect(info?.hasPreviousPage).toBe(false);
    expect(info?.hasNextPage).toBe(false);
  });

  it('should handle last page', () => {
    const response = {
      items: [],
      total: 50,
      page: 3,
      page_size: 20,
      pages: 3,
    };

    const info = extractPaginationInfo(response);

    expect(info?.hasPreviousPage).toBe(true);
    expect(info?.hasNextPage).toBe(false);
  });

  it('should return null for invalid response', () => {
    expect(extractPaginationInfo(null)).toBeNull();
    expect(extractPaginationInfo(undefined)).toBeNull();
    expect(extractPaginationInfo('string')).toBeNull();
  });
});

describe('getErrorMessage', () => {
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

  it('should extract message from error object with response.statusText', () => {
    const error = {
      response: {
        status: 404,
        statusText: 'Not Found',
      },
    };
    const message = getErrorMessage(error);
    expect(message).toBe('Not Found');
  });

  it('should return string as is', () => {
    const message = getErrorMessage('Error string');
    expect(message).toBe('Error string');
  });

  it('should handle null error gracefully', () => {
    const message = getErrorMessage(null);
    expect(message).toBe('An unknown error occurred');
  });

  it('should handle undefined error', () => {
    const message = getErrorMessage(undefined);
    expect(message).toBe('An unknown error occurred');
  });

  it('should handle object without message property', () => {
    const error = { code: 'ERROR_CODE' };
    const message = getErrorMessage(error);
    expect(message).toBe('An unknown error occurred');
  });

  it('should provide fallback for deeply nested API errors', () => {
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
    expect(typeof message).toBe('string');
  });
});
