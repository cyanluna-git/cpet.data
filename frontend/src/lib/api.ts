import axios from 'axios';
import { sampleTestData, sampleSubjects } from '@/utils/sampleData';

const API_BASE = '/api';

// axios 인스턴스 생성
const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' }
});

// 인터셉터로 JWT 토큰 자동 추가
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 데모 모드 체크
function isDemoMode() {
  return localStorage.getItem('demoMode') === 'true';
}

// API Functions
export const api = {
  // Auth
  async signIn(email: string, password: string) {
    if (isDemoMode()) {
      return { user: { email }, session: { access_token: 'demo-token' } };
    }
    // FastAPI OAuth2 Password Flow 형식
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    const response = await client.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });

    localStorage.setItem('access_token', response.data.access_token);
    return response.data;
  },

  async signOut() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('demoMode');
  },

  async getSession() {
    if (isDemoMode()) {
      return { access_token: 'demo-token' };
    }
    const token = localStorage.getItem('access_token');
    return token ? { access_token: token } : null;
  },

  async getCurrentUser() {
    if (isDemoMode()) {
      const role = localStorage.getItem('demoRole') || 'researcher';
      return {
        id: role === 'subject' ? '660e8400-e29b-41d4-a716-446655440001' : 'demo-researcher-1',
        email: role === 'subject' ? 'demo@subject.com' : 'demo@researcher.com',
        name: role === 'subject' ? '박용두' : '연구자 데모',
        role: role,
      };
    }
    const response = await client.get('/auth/me');
    return response.data;
  },

  async signUp(email: string, password: string, name: string, role: string) {
    if (isDemoMode()) {
      return { success: true };
    }
    const response = await client.post('/auth/register', { email, password, name, role });
    return response.data;
  },

  // Subjects
  async getSubjects() {
    if (isDemoMode()) {
      return sampleSubjects;
    }
    const response = await client.get('/subjects');
    return response.data;
  },

  async getSubject(id: string) {
    if (isDemoMode()) {
      return sampleSubjects.find(s => s.id === id) || sampleSubjects[0];
    }
    const response = await client.get(`/subjects/${id}`);
    return response.data;
  },

  async createSubject(subjectData: any) {
    if (isDemoMode()) {
      return { success: true, subject: subjectData };
    }
    const response = await client.post('/subjects', subjectData);
    return response.data;
  },

  // Tests
  async getTests() {
    if (isDemoMode()) {
      return [sampleTestData];
    }
    const response = await client.get('/tests');
    return response.data;
  },

  async getTest(id: string) {
    if (isDemoMode()) {
      return sampleTestData;
    }
    const response = await client.get(`/tests/${id}`);
    return response.data;
  },

  async createTest(testData: any) {
    if (isDemoMode()) {
      return { success: true, test: testData };
    }
    const response = await client.post('/tests', testData);
    return response.data;
  },

  async updateTest(id: string, updates: any) {
    if (isDemoMode()) {
      return { success: true, test: { id, ...updates } };
    }
    const response = await client.put(`/tests/${id}`, updates);
    return response.data;
  },

  async deleteTest(id: string) {
    if (isDemoMode()) {
      return { success: true };
    }
    const response = await client.delete(`/tests/${id}`);
    return response.data;
  },

  // Cohort Analysis
  async getCohortStats(filters: any) {
    if (isDemoMode()) {
      // 데모 모드에서 샘플 통계 반환
      return {
        totalSubjects: sampleSubjects.length,
        avgVO2Max: 45.2,
        avgFatMaxHR: 128,
        subjects: sampleSubjects,
      };
    }
    const response = await client.post('/cohort/stats', { filters });
    return response.data;
  },
};
