/** Frontend environment configuration and constants. */

// API Configuration
export const API_CONFIG = {
  // Base URL for API calls (determined at build time via import.meta.env)
  BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:8100',
  
  // API endpoints
  ENDPOINTS: {
    AUTH: '/api/auth',
    SUBJECTS: '/api/subjects',
    TESTS: '/api/tests',
    COHORTS: '/api/cohorts',
  },
  
  // Timeout settings (ms)
  TIMEOUT: 30000,
  
  // Retry configuration
  RETRY: {
    MAX_ATTEMPTS: 3,
    INITIAL_DELAY: 1000,
    MAX_DELAY: 10000,
  },
};

// Application Constants
export const APP_CONFIG = {
  // Application name
  APP_NAME: 'CPET Platform',
  
  // Version
  VERSION: '1.0.0',
  
  // Environment
  ENV: import.meta.env.MODE,
  
  // Debug mode
  DEBUG: import.meta.env.DEV,
};

// Pagination
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
  MIN_PAGE_SIZE: 5,
};

// User roles
export const ROLES = {
  ADMIN: 'admin',
  RESEARCHER: 'researcher',
  SUBJECT: 'subject',
} as const;

export type Role = typeof ROLES[keyof typeof ROLES];

// User role permissions matrix
export const ROLE_PERMISSIONS: Record<Role, string[]> = {
  [ROLES.ADMIN]: ['read:all', 'write:all', 'delete:all', 'manage:users'],
  [ROLES.RESEARCHER]: ['read:subjects', 'read:tests', 'write:tests', 'read:cohorts'],
  [ROLES.SUBJECT]: ['read:own', 'read:own_tests'],
};

// Local storage keys
export const STORAGE_KEYS = {
  AUTH_TOKEN: 'cpet_auth_token',
  USER: 'cpet_user',
  PREFERENCES: 'cpet_preferences',
  LAST_ROUTE: 'cpet_last_route',
} as const;

// Request/Response timeouts
export const TIMEOUTS = {
  SHORT: 5000,    // 5 seconds
  MEDIUM: 15000,  // 15 seconds
  LONG: 30000,    // 30 seconds
  UPLOAD: 120000, // 2 minutes
} as const;

// Error codes
export const ERROR_CODES = {
  NETWORK_ERROR: 'NETWORK_ERROR',
  TIMEOUT: 'TIMEOUT',
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  NOT_FOUND: 'NOT_FOUND',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  SERVER_ERROR: 'SERVER_ERROR',
  UNKNOWN: 'UNKNOWN',
} as const;

// Feature flags
export const FEATURES = {
  DEMO_MODE: import.meta.env.VITE_DEMO_MODE === 'true',
  ANALYTICS: import.meta.env.VITE_ANALYTICS === 'true',
  ERROR_REPORTING: import.meta.env.VITE_ERROR_REPORTING === 'true',
};

// Log levels
export const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
  NONE: 4,
} as const;

// Current log level based on environment
export const LOG_LEVEL = import.meta.env.DEV ? LOG_LEVELS.DEBUG : LOG_LEVELS.WARN;

/**
 * Get configuration value with fallback.
 * @param key - Config key
 * @param defaultValue - Default value if not found
 * @returns Configuration value or default
 */
export function getConfig<T = string>(key: string, defaultValue?: T): T | string | undefined {
  const value = import.meta.env[`VITE_${key.toUpperCase()}`];
  return value !== undefined ? value : defaultValue;
}

/**
 * Check if feature is enabled.
 * @param feature - Feature name
 * @returns Whether feature is enabled
 */
export function isFeatureEnabled(feature: keyof typeof FEATURES): boolean {
  return FEATURES[feature];
}

/**
 * Get API URL for endpoint.
 * @param endpoint - API endpoint path
 * @returns Full API URL
 */
export function getApiUrl(endpoint: string): string {
  const base = API_CONFIG.BASE_URL;
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
}

/**
 * Check if user has permission.
 * @param userRole - User's role
 * @param permission - Required permission
 * @returns Whether user has permission
 */
export function hasPermission(userRole: Role, permission: string): boolean {
  const permissions = ROLE_PERMISSIONS[userRole] || [];
  
  // Admin has all permissions
  if (userRole === ROLES.ADMIN) return true;
  
  return permissions.includes(permission);
}
