import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { api } from '@/lib/api';

describe('API Client', () => {
  beforeEach(() => {
    // Clear localStorage
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Authentication', () => {
    it('should have signIn method', () => {
      expect(typeof api.signIn).toBe('function');
    });

    it('should have signOut method', () => {
      expect(typeof api.signOut).toBe('function');
    });

    it('should have getSession method', () => {
      expect(typeof api.getSession).toBe('function');
    });

    it('should have getCurrentUser method', () => {
      expect(typeof api.getCurrentUser).toBe('function');
    });

    it('should return null session when no token', async () => {
      const session = await api.getSession();
      expect(session).toBeNull();
    });

    it('should return session when token exists', async () => {
      localStorage.setItem('access_token', 'test-token');
      const session = await api.getSession();
      expect(session).toEqual({ access_token: 'test-token' });
    });

    it('should clear token on signOut', async () => {
      localStorage.setItem('access_token', 'test-token');
      await api.signOut();
      expect(localStorage.getItem('access_token')).toBeNull();
    });

    it('should clear demoMode on signOut', async () => {
      localStorage.setItem('demoMode', 'true');
      await api.signOut();
      expect(localStorage.getItem('demoMode')).toBeNull();
    });
  });

  describe('Subjects API', () => {
    it('should have getSubjects method', () => {
      expect(typeof api.getSubjects).toBe('function');
    });

    it('should have getSubject method', () => {
      expect(typeof api.getSubject).toBe('function');
    });

    it('should have getSubjectTests method', () => {
      expect(typeof api.getSubjectTests).toBe('function');
    });

    it('should have createSubject method', () => {
      expect(typeof api.createSubject).toBe('function');
    });

    it('should have updateSubject method', () => {
      expect(typeof api.updateSubject).toBe('function');
    });

    it('should have deleteSubject method', () => {
      expect(typeof api.deleteSubject).toBe('function');
    });
  });

  describe('Tests API', () => {
    it('should have getTests method', () => {
      expect(typeof api.getTests).toBe('function');
    });

    it('should have getTest method', () => {
      expect(typeof api.getTest).toBe('function');
    });

    it('should have getTestAnalysis method', () => {
      expect(typeof api.getTestAnalysis).toBe('function');
    });

    it('should have uploadTestAuto method', () => {
      expect(typeof api.uploadTestAuto).toBe('function');
    });

    it('should have uploadTest method', () => {
      expect(typeof api.uploadTest).toBe('function');
    });

    it('should have updateTest method', () => {
      expect(typeof api.updateTest).toBe('function');
    });

    it('should have deleteTest method', () => {
      expect(typeof api.deleteTest).toBe('function');
    });
  });

  describe('Admin API', () => {
    it('should have adminListUsers method', () => {
      expect(typeof api.adminListUsers).toBe('function');
    });

    it('should have adminGetStats method', () => {
      expect(typeof api.adminGetStats).toBe('function');
    });

    it('should have adminCreateUser method', () => {
      expect(typeof api.adminCreateUser).toBe('function');
    });

    it('should have adminUpdateUser method', () => {
      expect(typeof api.adminUpdateUser).toBe('function');
    });

    it('should have adminDeleteUser method', () => {
      expect(typeof api.adminDeleteUser).toBe('function');
    });
  });

  describe('Metabolism API', () => {
    it('should have getProcessedMetabolism method', () => {
      expect(typeof api.getProcessedMetabolism).toBe('function');
    });

    it('should have saveProcessedMetabolism method', () => {
      expect(typeof api.saveProcessedMetabolism).toBe('function');
    });

    it('should have deleteProcessedMetabolism method', () => {
      expect(typeof api.deleteProcessedMetabolism).toBe('function');
    });
  });

  describe('Cohort API', () => {
    it('should have getCohortSummary method', () => {
      expect(typeof api.getCohortSummary).toBe('function');
    });

    it('should have getCohortDistribution method', () => {
      expect(typeof api.getCohortDistribution).toBe('function');
    });

    it('should have getPercentile method', () => {
      expect(typeof api.getPercentile).toBe('function');
    });

    it('should have getGroupComparison method', () => {
      expect(typeof api.getGroupComparison).toBe('function');
    });

    it('should have getOverallStats method', () => {
      expect(typeof api.getOverallStats).toBe('function');
    });
  });

  describe('Time Series & Metrics API', () => {
    it('should have getTimeSeries method', () => {
      expect(typeof api.getTimeSeries).toBe('function');
    });

    it('should have getTestMetrics method', () => {
      expect(typeof api.getTestMetrics).toBe('function');
    });
  });
});

describe('API Response Types', () => {
  it('should export api object', async () => {
    const apiModule = await import('@/lib/api');
    expect(apiModule.api).toBeDefined();
  });

  it('should export API_BASE constant', async () => {
    const apiModule = await import('@/lib/api');
    expect(apiModule.API_BASE).toBeDefined();
    expect(typeof apiModule.API_BASE).toBe('string');
  });
});
