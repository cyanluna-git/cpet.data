"""Unit tests for environment configuration."""

import { describe, it, expect, beforeEach, vi } from 'vitest';
import * as env from '@/config/env';

describe('Configuration', () => {
  describe('API_CONFIG', () => {
    it('should have base URL configured', () => {
      expect(env.API_CONFIG.BASE_URL).toBeDefined();
      expect(typeof env.API_CONFIG.BASE_URL).toBe('string');
    });

    it('should have endpoints defined', () => {
      expect(env.API_CONFIG.ENDPOINTS.AUTH).toBeDefined();
      expect(env.API_CONFIG.ENDPOINTS.SUBJECTS).toBeDefined();
      expect(env.API_CONFIG.ENDPOINTS.TESTS).toBeDefined();
    });

    it('should have retry configuration', () => {
      expect(env.API_CONFIG.RETRY.MAX_ATTEMPTS).toBeGreaterThan(0);
      expect(env.API_CONFIG.RETRY.INITIAL_DELAY).toBeGreaterThan(0);
      expect(env.API_CONFIG.RETRY.MAX_DELAY).toBeGreaterThanOrEqual(env.API_CONFIG.RETRY.INITIAL_DELAY);
    });
  });

  describe('APP_CONFIG', () => {
    it('should have app name', () => {
      expect(env.APP_CONFIG.APP_NAME).toBeDefined();
      expect(typeof env.APP_CONFIG.APP_NAME).toBe('string');
    });

    it('should have version', () => {
      expect(env.APP_CONFIG.VERSION).toBeDefined();
      expect(/\d+\.\d+\.\d+/.test(env.APP_CONFIG.VERSION)).toBe(true);
    });

    it('should have environment', () => {
      expect(env.APP_CONFIG.ENV).toBeDefined();
      expect(['development', 'production', 'test']).toContain(env.APP_CONFIG.ENV);
    });
  });

  describe('ROLES', () => {
    it('should define all roles', () => {
      expect(env.ROLES.ADMIN).toBe('admin');
      expect(env.ROLES.RESEARCHER).toBe('researcher');
      expect(env.ROLES.SUBJECT).toBe('subject');
    });
  });

  describe('ROLE_PERMISSIONS', () => {
    it('should define permissions for admin', () => {
      const permissions = env.ROLE_PERMISSIONS['admin'];
      expect(permissions).toContain('read:all');
      expect(permissions).toContain('write:all');
    });

    it('should define permissions for researcher', () => {
      const permissions = env.ROLE_PERMISSIONS['researcher'];
      expect(permissions.length).toBeGreaterThan(0);
      expect(typeof permissions[0]).toBe('string');
    });

    it('should define permissions for subject', () => {
      const permissions = env.ROLE_PERMISSIONS['subject'];
      expect(permissions.length).toBeGreaterThan(0);
    });
  });

  describe('STORAGE_KEYS', () => {
    it('should have storage keys defined', () => {
      expect(env.STORAGE_KEYS.AUTH_TOKEN).toBeDefined();
      expect(env.STORAGE_KEYS.USER).toBeDefined();
      expect(env.STORAGE_KEYS.PREFERENCES).toBeDefined();
    });

    it('should have unique keys', () => {
      const keys = Object.values(env.STORAGE_KEYS);
      const uniqueKeys = new Set(keys);
      expect(uniqueKeys.size).toBe(keys.length);
    });
  });

  describe('TIMEOUTS', () => {
    it('should have timeout values', () => {
      expect(env.TIMEOUTS.SHORT).toBeGreaterThan(0);
      expect(env.TIMEOUTS.MEDIUM).toBeGreaterThan(env.TIMEOUTS.SHORT);
      expect(env.TIMEOUTS.LONG).toBeGreaterThan(env.TIMEOUTS.MEDIUM);
    });
  });

  describe('hasPermission', () => {
    it('should return true for admin with any permission', () => {
      expect(env.hasPermission('admin', 'read:all')).toBe(true);
      expect(env.hasPermission('admin', 'write:all')).toBe(true);
      expect(env.hasPermission('admin', 'any:permission')).toBe(true);
    });

    it('should return true for researcher with allowed permissions', () => {
      expect(env.hasPermission('researcher', 'read:subjects')).toBe(true);
    });

    it('should return false for subject with researcher permissions', () => {
      expect(env.hasPermission('subject', 'read:subjects')).toBe(false);
    });

    it('should return false for subject with unauthorized permission', () => {
      expect(env.hasPermission('subject', 'write:all')).toBe(false);
    });
  });

  describe('getApiUrl', () => {
    it('should construct API URL with endpoint', () => {
      const url = env.getApiUrl('/api/subjects');
      expect(url).toContain('api/subjects');
    });

    it('should handle endpoint with or without leading slash', () => {
      const url1 = env.getApiUrl('/api/subjects');
      const url2 = env.getApiUrl('api/subjects');
      expect(url1).toBe(url2);
    });

    it('should include base URL', () => {
      const url = env.getApiUrl('/api/subjects');
      expect(url.startsWith('http')).toBe(true);
    });
  });

  describe('isFeatureEnabled', () => {
    it('should return boolean for feature flags', () => {
      const demoEnabled = env.isFeatureEnabled('DEMO_MODE');
      expect(typeof demoEnabled).toBe('boolean');
    });

    it('should handle all feature keys', () => {
      expect(() => env.isFeatureEnabled('DEMO_MODE')).not.toThrow();
      expect(() => env.isFeatureEnabled('ANALYTICS')).not.toThrow();
      expect(() => env.isFeatureEnabled('ERROR_REPORTING')).not.toThrow();
    });
  });

  describe('ERROR_CODES', () => {
    it('should define common error codes', () => {
      expect(env.ERROR_CODES.NETWORK_ERROR).toBeDefined();
      expect(env.ERROR_CODES.TIMEOUT).toBeDefined();
      expect(env.ERROR_CODES.UNAUTHORIZED).toBeDefined();
      expect(env.ERROR_CODES.VALIDATION_ERROR).toBeDefined();
    });
  });

  describe('LOG_LEVELS', () => {
    it('should have log levels in correct order', () => {
      expect(env.LOG_LEVELS.DEBUG).toBeLessThan(env.LOG_LEVELS.INFO);
      expect(env.LOG_LEVELS.INFO).toBeLessThan(env.LOG_LEVELS.WARN);
      expect(env.LOG_LEVELS.WARN).toBeLessThan(env.LOG_LEVELS.ERROR);
      expect(env.LOG_LEVELS.ERROR).toBeLessThan(env.LOG_LEVELS.NONE);
    });
  });
});
