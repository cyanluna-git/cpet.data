import axios, { AxiosError } from 'axios';
import { sampleTestData, sampleSubjects } from '@/utils/sampleData';

// 환경변수에서 API URL 가져오기 (기본값: /api)
// - 상대경로('/api')면 Vite proxy를 사용
// - 절대 URL('http://host:port')이면 FastAPI가 /api prefix를 쓰므로 '/api'를 자동으로 붙임
const RAW_API_BASE: string = import.meta.env.VITE_API_URL || '/api';
const API_BASE = RAW_API_BASE === '/api' || RAW_API_BASE.endsWith('/api')
  ? RAW_API_BASE
  : `${RAW_API_BASE.replace(/\/+$/, '')}/api`;

// axios 인스턴스 생성
const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// 요청 인터셉터: JWT 토큰 자동 추가
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터: 401 에러 시 자동 로그아웃
client.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('demoMode');
      // 로그인 페이지로 리다이렉트 (선택적)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// 데모 모드 체크
function isDemoMode() {
  return localStorage.getItem('demoMode') === 'true';
}

function roleFromBackend(role: string): 'admin' | 'researcher' | 'subject' {
  if (role === 'user') return 'subject';
  if (role === 'subject') return 'subject';
  if (role === 'admin' || role === 'researcher') return role;
  return 'researcher';
}

function roleToBackend(role: string): 'admin' | 'researcher' | 'user' {
  if (role === 'subject') return 'user';
  if (role === 'admin' || role === 'researcher' || role === 'user') return role;
  return 'user';
}

export interface AdminUser {
  user_id: string;
  email: string;
  role: 'admin' | 'researcher' | 'user';
  subject_id?: string | null;
  is_active: boolean;
  last_login?: string | null;
  created_at: string;
}

export interface AdminStats {
  users_total: number;
  users_active: number;
  users_inactive: number;
  users_by_role: Record<string, number>;
  subjects_total: number;
  tests_total: number;
}

// 타입 정의
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Subject {
  id: string;
  research_id: string;
  encrypted_name?: string | null;
  name?: string;
  birth_year?: number;
  gender?: string;
  job_category?: string;
  height_cm?: number;
  weight_kg?: number;
  training_level?: string;
  notes?: string;
  test_count?: number;
  created_at?: string;
  updated_at?: string;

  // Legacy/compat fields (some UI/sample data still uses these)
  subject_code?: string;
  birth_date?: string;
  group?: string;
}

export interface CPETTest {
  id: string;
  subject_id: string;
  test_date: string;
  test_type?: string;
  protocol?: string;
  duration_seconds?: number;
  status: string;
  notes?: string;
  vo2_max?: number;
  vo2_max_kg?: number;
  hr_max?: number;
  created_at: string;
}

export interface TimeSeriesData {
  test_id: string;
  signals: string[];
  interval: string;
  method: string;
  timestamps: number[];
  data: Record<string, number[]>;
  total_points: number;
}

export interface TestMetrics {
  test_id: string;
  vo2_max?: number;
  vo2_max_kg?: number;
  hr_max?: number;
  ve_max?: number;
  rer_max?: number;
  vt1?: { vo2: number; hr: number; time: number };
  vt2?: { vo2: number; hr: number; time: number };
  fat_max?: { fat_oxidation: number; hr: number; vo2: number };
}

export interface CohortSummary {
  total_subjects: number;
  total_tests: number;
  filters_applied: Record<string, any>;
  metrics: Record<string, {
    count: number;
    mean: number;
    std: number;
    min: number;
    max: number;
    median: number;
  }>;
}

// API Functions
export const api = {
  // =====================
  // Auth
  // =====================
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
    localStorage.removeItem('demoRole');
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
    const raw = response.data as any;
    // backend(UserResponse): user_id/email/role/is_active/last_login/created_at
    return {
      id: raw.user_id ?? raw.id,
      email: raw.email,
      name: (raw.email || '').split('@')[0] || raw.email,
      role: roleFromBackend(raw.role),
    };
  },

  async signUp(email: string, password: string, name: string, role: string) {
    if (isDemoMode()) {
      return { success: true };
    }
    // backend는 name을 저장하지 않으므로 전송하지 않음
    const response = await client.post('/auth/register', { email, password, role: roleToBackend(role) });
    return response.data;
  },

  // =====================
  // Admin
  // =====================
  async adminGetStats(): Promise<AdminStats> {
    if (isDemoMode()) {
      return {
        users_total: 3,
        users_active: 3,
        users_inactive: 0,
        users_by_role: { admin: 1, researcher: 1, user: 1 },
        subjects_total: sampleSubjects.length,
        tests_total: 1,
      };
    }
    const response = await client.get('/admin/stats');
    return response.data;
  },

  async adminListUsers(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    role?: string;
    is_active?: boolean;
    sort_by?: 'created_at' | 'last_login' | 'email' | 'role';
    sort_order?: 'asc' | 'desc';
  }): Promise<PaginatedResponse<AdminUser>> {
    if (isDemoMode()) {
      const now = new Date().toISOString();
      const items: AdminUser[] = [
        { user_id: 'demo-admin-1', email: 'admin@demo.local', role: 'admin', is_active: true, created_at: now },
        { user_id: 'demo-researcher-1', email: 'researcher@demo.local', role: 'researcher', is_active: true, created_at: now },
        { user_id: 'demo-user-1', email: 'subject@demo.local', role: 'user', is_active: true, created_at: now },
      ];
      return { items, total: items.length, page: 1, page_size: 20, total_pages: 1 };
    }
    const response = await client.get('/admin/users', { params });
    return response.data;
  },

  async adminCreateUser(data: { email: string; password: string; role: string; subject_id?: string | null }): Promise<AdminUser> {
    if (isDemoMode()) {
      return {
        user_id: `demo-${crypto.randomUUID()}`,
        email: data.email,
        role: roleToBackend(data.role),
        subject_id: data.subject_id ?? null,
        is_active: true,
        created_at: new Date().toISOString(),
        last_login: null,
      };
    }
    const response = await client.post('/admin/users', {
      ...data,
      role: roleToBackend(data.role),
    });
    return response.data;
  },

  async adminUpdateUser(userId: string, data: Partial<{ email: string; password: string; role: string; is_active: boolean; subject_id: string | null }>): Promise<AdminUser> {
    if (isDemoMode()) {
      return {
        user_id: userId,
        email: data.email ?? 'demo@updated.local',
        role: roleToBackend(data.role ?? 'user'),
        subject_id: data.subject_id ?? null,
        is_active: data.is_active ?? true,
        created_at: new Date().toISOString(),
        last_login: null,
      };
    }
    const response = await client.put(`/admin/users/${userId}`, {
      ...data,
      role: data.role ? roleToBackend(data.role) : undefined,
    });
    return response.data;
  },

  async adminDeleteUser(userId: string): Promise<void> {
    if (isDemoMode()) return;
    await client.delete(`/admin/users/${userId}`);
  },

  async refreshToken() {
    const token = localStorage.getItem('access_token');
    if (!token) return null;
    
    const response = await client.post('/auth/refresh');
    localStorage.setItem('access_token', response.data.access_token);
    return response.data;
  },

  // =====================
  // Subjects
  // =====================
  async getSubjects(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    gender?: string;
    min_age?: number;
    max_age?: number;
    group?: string;
    sort_by?: string;
    sort_order?: string;
  }): Promise<PaginatedResponse<Subject>> {
    if (isDemoMode()) {
      return {
        items: sampleSubjects as any,
        total: sampleSubjects.length,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
    }
    const response = await client.get('/subjects', { params });
    return response.data;
  },

  async getSubject(id: string): Promise<Subject & { tests: CPETTest[] }> {
    if (isDemoMode()) {
      const subject = sampleSubjects.find(s => s.id === id) || sampleSubjects[0];
      return { ...subject, tests: [sampleTestData] } as any;
    }
    const response = await client.get(`/subjects/${id}`);
    return response.data;
  },

  async createSubject(data: Partial<Subject> & { research_id: string }): Promise<Subject> {
    if (isDemoMode()) {
      return {
        id: 'demo-new-subject',
        ...data,
        created_at: data.created_at || new Date().toISOString(),
        updated_at: data.updated_at || new Date().toISOString(),
      } as Subject;
    }

    // Backend expects SubjectCreate schema (research_id + optional fields)
    const payload: Record<string, any> = {
      research_id: data.research_id,
      encrypted_name: data.encrypted_name ?? data.name,
      birth_year: data.birth_year,
      gender: data.gender,
      height_cm: data.height_cm,
      weight_kg: data.weight_kg,
      notes: data.notes,
    };

    // Drop undefined to keep payload clean
    Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);

    const response = await client.post('/subjects', payload);
    return response.data;
  },

  async updateSubject(id: string, data: Partial<Subject>): Promise<Subject> {
    if (isDemoMode()) {
      return { id, ...data } as Subject;
    }
    const response = await client.patch(`/subjects/${id}`, data);
    return response.data;
  },

  async deleteSubject(id: string): Promise<void> {
    if (isDemoMode()) return;
    await client.delete(`/subjects/${id}`);
  },

  // =====================
  // Tests
  // =====================
  async getTests(params?: {
    page?: number;
    page_size?: number;
    subject_id?: string;
    test_type?: string;
  }): Promise<PaginatedResponse<CPETTest>> {
    if (isDemoMode()) {
      return {
        items: [sampleTestData] as any,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
    }
    const response = await client.get('/tests', { params });
    return response.data;
  },

  async getTest(id: string): Promise<CPETTest> {
    if (isDemoMode()) {
      return sampleTestData as any;
    }
    const response = await client.get(`/tests/${id}`);
    return response.data;
  },

  async uploadTest(file: File, subjectId: string, notes?: string): Promise<{
    test: CPETTest;
    breath_data_count: number;
    message: string;
  }> {
    if (isDemoMode()) {
      return {
        test: sampleTestData as any,
        breath_data_count: 500,
        message: 'Demo upload successful',
      };
    }
    const formData = new FormData();
    formData.append('file', file);
    formData.append('subject_id', subjectId);
    if (notes) formData.append('notes', notes);

    const response = await client.post('/tests/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000, // 2분 타임아웃 (대용량 파일)
    });
    return response.data;
  },

  async updateTest(id: string, data: Partial<CPETTest>): Promise<CPETTest> {
    if (isDemoMode()) {
      return { id, ...data } as CPETTest;
    }
    const response = await client.patch(`/tests/${id}`, data);
    return response.data;
  },

  async deleteTest(id: string): Promise<void> {
    if (isDemoMode()) return;
    await client.delete(`/tests/${id}`);
  },

  // =====================
  // Time Series & Metrics
  // =====================
  async getTimeSeries(testId: string, params?: {
    signals?: string;
    interval?: string;
    method?: string;
    start_time?: number;
    end_time?: number;
    max_points?: number;
  }): Promise<TimeSeriesData> {
    if (isDemoMode()) {
      // 데모 시계열 데이터 생성
      const signals = (params?.signals || 'VO2,VCO2,HR').split(',');
      const points = 100;
      const timestamps = Array.from({ length: points }, (_, i) => i * 6);
      const data: Record<string, number[]> = {};
      signals.forEach(signal => {
        data[signal] = Array.from({ length: points }, () => Math.random() * 50 + 20);
      });
      return {
        test_id: testId,
        signals,
        interval: params?.interval || '1s',
        method: params?.method || 'mean',
        timestamps,
        data,
        total_points: points,
      };
    }
    const response = await client.get(`/tests/${testId}/series`, { params });
    return response.data;
  },

  async getTestMetrics(testId: string): Promise<TestMetrics> {
    if (isDemoMode()) {
      return {
        test_id: testId,
        vo2_max: 3.85,
        vo2_max_kg: 52.3,
        hr_max: 185,
        ve_max: 145.2,
        rer_max: 1.15,
        vt1: { vo2: 2.1, hr: 135, time: 360 },
        vt2: { vo2: 3.2, hr: 165, time: 540 },
        fat_max: { fat_oxidation: 0.65, hr: 128, vo2: 1.85 },
      };
    }
    const response = await client.get(`/tests/${testId}/metrics`);
    return response.data;
  },

  // =====================
  // Subject Tests (alternative path)
  // =====================
  async getSubjectTests(subjectId: string, params?: {
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<CPETTest>> {
    if (isDemoMode()) {
      return {
        items: [sampleTestData] as any,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
    }
    const response = await client.get(`/subjects/${subjectId}/tests`, { params });
    return response.data;
  },

  // =====================
  // Cohort Analysis
  // =====================
  async getCohortSummary(params?: {
    gender?: string;
    min_age?: number;
    max_age?: number;
    group?: string;
    test_type?: string;
    metrics?: string;
  }): Promise<CohortSummary> {
    if (isDemoMode()) {
      return {
        total_subjects: sampleSubjects.length,
        total_tests: 10,
        filters_applied: params || {},
        metrics: {
          VO2max: { count: 10, mean: 45.2, std: 8.5, min: 32.1, max: 58.7, median: 44.5 },
          VO2max_kg: { count: 10, mean: 52.3, std: 7.2, min: 42.0, max: 65.0, median: 51.8 },
          HRmax: { count: 10, mean: 182, std: 12, min: 165, max: 198, median: 183 },
        },
      };
    }
    const response = await client.get('/cohorts/summary', { params });
    return response.data;
  },

  async getCohortDistribution(params: {
    metric: string;
    bins?: number;
    gender?: string;
    min_age?: number;
    max_age?: number;
    group?: string;
    test_type?: string;
  }) {
    if (isDemoMode()) {
      const bins = params.bins || 10;
      return {
        metric: params.metric,
        bins: Array.from({ length: bins }, (_, i) => ({
          bin_start: 30 + i * 4,
          bin_end: 34 + i * 4,
          count: Math.floor(Math.random() * 10) + 1,
        })),
        total_count: 50,
        filters_applied: params,
      };
    }
    const response = await client.get('/cohorts/distribution', { params });
    return response.data;
  },

  async getPercentile(params: {
    subject_id: string;
    test_id?: string;
    metrics?: string;
    compare_gender?: boolean;
    compare_age_range?: number;
  }) {
    if (isDemoMode()) {
      const metrics = (params.metrics || 'VO2max,VO2max_kg').split(',');
      return {
        subject_id: params.subject_id,
        test_id: params.test_id || 'demo-test',
        percentiles: Object.fromEntries(
          metrics.map(m => [m, { value: 45, percentile: 72 }])
        ),
        comparison_group: { total: 50, gender: 'M', age_range: '20-30' },
      };
    }
    const response = await client.get('/cohorts/percentile', { params });
    return response.data;
  },

  async getGroupComparison(params: {
    group_by: string;
    metrics?: string;
    test_type?: string;
  }) {
    if (isDemoMode()) {
      return {
        group_by: params.group_by,
        groups: [
          { group: 'M', count: 30, metrics: { VO2max: { mean: 48.5, std: 7.2 } } },
          { group: 'F', count: 20, metrics: { VO2max: { mean: 42.1, std: 6.8 } } },
        ],
        filters_applied: params,
      };
    }
    const response = await client.get('/cohorts/comparison', { params });
    return response.data;
  },

  async getOverallStats() {
    if (isDemoMode()) {
      return {
        total_subjects: sampleSubjects.length,
        total_tests: 15,
        total_breath_data_points: 75000,
        gender_distribution: { M: 8, F: 7 },
        age_distribution: { '20s': 5, '30s': 6, '40s': 4 },
      };
    }
    const response = await client.get('/cohorts/stats');
    return response.data;
  },

  // =====================
  // Legacy compatibility (deprecated)
  // =====================
  /** @deprecated Use getCohortSummary instead */
  async getCohortStats(filters: any) {
    console.warn('api.getCohortStats is deprecated. Use api.getCohortSummary instead.');
    return this.getCohortSummary(filters);
  },

  /** @deprecated Use uploadTest instead */
  async createTest(testData: any) {
    console.warn('api.createTest is deprecated. Use api.uploadTest instead.');
    if (isDemoMode()) {
      return { success: true, test: testData };
    }
    const response = await client.post('/tests', testData);
    return response.data;
  },
};
