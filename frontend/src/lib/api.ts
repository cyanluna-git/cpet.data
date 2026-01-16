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

// Test Analysis Types (대사 프로파일 차트용)
export interface PhaseInfo {
  phase: string;
  start_sec: number;
  end_sec: number;
}

export interface PhaseBoundaries {
  rest_end_sec?: number;
  warmup_end_sec?: number;
  exercise_end_sec?: number;
  peak_sec?: number;
  total_duration_sec?: number;
  phases: PhaseInfo[];
}

export interface PhaseMetrics {
  duration_sec?: number;
  data_points?: number;
  avg_hr?: number;
  max_hr?: number;
  avg_vo2?: number;
  max_vo2?: number;
  avg_rer?: number;
  max_rer?: number;
  avg_fat_oxidation?: number;
  max_fat_oxidation?: number;
  avg_cho_oxidation?: number;
  max_cho_oxidation?: number;
  avg_bike_power?: number;
  max_bike_power?: number;
}

export interface FatMaxInfo {
  fat_max_g_min?: number;
  fat_max_hr?: number;
  fat_max_watt?: number;
  fat_max_vo2?: number;
  fat_max_rer?: number;
  fat_max_time_sec?: number;
}

export interface VO2MaxInfo {
  vo2_max?: number;
  vo2_max_rel?: number;
  vco2_max?: number;
  hr_max?: number;
  rer_at_max?: number;
  vo2_max_time_sec?: number;
}

export interface MetabolismDataPoint {
  time_sec: number;
  power?: number;
  hr?: number;
  vo2?: number;
  vco2?: number;
  rer?: number;
  fat_oxidation?: number;
  cho_oxidation?: number;
  fat_kcal_day?: number;
  cho_kcal_day?: number;
  phase?: string;
}

// Processed Metabolism Data Types (LOESS smoothing, binning)
export interface ProcessedDataPoint {
  power: number;
  fat_oxidation: number | null;
  cho_oxidation: number | null;
  count?: number;  // binned data only
}

export interface ProcessedSeries {
  raw: ProcessedDataPoint[];
  binned: ProcessedDataPoint[];
  smoothed: ProcessedDataPoint[];
}

export interface FatMaxMarker {
  power: number;           // FatMax 지점 파워 (W)
  mfo: number;             // Maximum Fat Oxidation (g/min)
  zone_min: number;        // FatMax zone 하한 (W)
  zone_max: number;        // FatMax zone 상한 (W)
}

export interface CrossoverMarker {
  power: number | null;         // Crossover 지점 파워 (W), 없으면 null
  fat_value: number | null;     // 교차 지점 FatOx 값
  cho_value: number | null;     // 교차 지점 CHOOx 값
}

export interface MetabolicMarkers {
  fat_max: FatMaxMarker;
  crossover: CrossoverMarker;
}

export interface TestAnalysis {
  test_id: string;
  subject_id: string;
  test_date: string;
  protocol_type?: string;
  calc_method: string;
  phase_boundaries?: PhaseBoundaries;
  phase_metrics?: Record<string, PhaseMetrics>;
  fatmax?: FatMaxInfo;
  vo2max?: VO2MaxInfo;
  vt1_hr?: number;
  vt1_vo2?: number;
  vt2_hr?: number;
  vt2_vo2?: number;
  timeseries: MetabolismDataPoint[];
  timeseries_interval: string;
  total_fat_burned_g?: number;
  total_cho_burned_g?: number;
  avg_rer?: number;
  exercise_duration_sec?: number;
  // Processed data (LOESS smoothing, binning)
  processed_series?: ProcessedSeries;
  metabolic_markers?: MetabolicMarkers;
  analysis_warnings?: string[];
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

  /**
   * 테스트 분석 결과 조회 (대사 프로파일 차트용)
   * - phase_boundaries: 구간 경계
   * - phase_metrics: 구간별 메트릭
   * - fatmax/vo2max: 상세 정보
   * - timeseries: 다운샘플된 시계열 데이터
   * - processed_series: LOESS smoothing, binning 처리된 데이터
   * - metabolic_markers: FatMax zone, Crossover point 마커
   */
  async getTestAnalysis(
    testId: string,
    interval: string = '5s',
    include_processed: boolean = true,
    loess_frac: number = 0.25,
    bin_size: number = 10,
    aggregation_method: string = 'median'
  ): Promise<TestAnalysis> {
    if (isDemoMode()) {
      // 데모 분석 데이터 생성
      const timeseries: MetabolismDataPoint[] = [];
      for (let t = 0; t <= 1500; t += 5) {
        const progress = t / 1500;
        const power = t < 180 ? 0 : t < 360 ? 50 + (t - 180) * 0.5 : Math.min(50 + (t - 180) * 0.3, 260);
        const hr = 70 + progress * 120;
        const vo2 = 300 + progress * 3500;
        const fatOx = t < 180 ? 0.1 : Math.max(0.05, 0.6 - Math.pow(progress - 0.4, 2) * 2);
        const choOx = t < 180 ? 0.1 : 0.2 + progress * 1.5;

        let phase = 'Rest';
        if (t >= 180 && t < 360) phase = 'Warm-up';
        else if (t >= 360 && t < 1320) phase = 'Exercise';
        else if (t >= 1320 && t < 1380) phase = 'Peak';
        else if (t >= 1380) phase = 'Recovery';

        timeseries.push({
          time_sec: t,
          power: Math.round(power),
          hr: Math.round(hr),
          vo2: Math.round(vo2),
          vco2: Math.round(vo2 * 0.9),
          rer: 0.85 + progress * 0.25,
          fat_oxidation: fatOx,
          cho_oxidation: choOx,
          fat_kcal_day: fatOx * 9.75 * 60 * 24,
          cho_kcal_day: choOx * 4.07 * 60 * 24,
          phase,
        });
      }

      return {
        test_id: testId,
        subject_id: 'demo-subject',
        test_date: new Date().toISOString(),
        protocol_type: 'MIX',
        calc_method: 'Frayn',
        phase_boundaries: {
          rest_end_sec: 180,
          warmup_end_sec: 360,
          exercise_end_sec: 1320,
          peak_sec: 1320,
          total_duration_sec: 1500,
          phases: [
            { phase: 'Rest', start_sec: 0, end_sec: 180 },
            { phase: 'Warm-up', start_sec: 180, end_sec: 360 },
            { phase: 'Exercise', start_sec: 360, end_sec: 1320 },
            { phase: 'Peak', start_sec: 1320, end_sec: 1380 },
            { phase: 'Recovery', start_sec: 1380, end_sec: 1500 },
          ],
        },
        phase_metrics: {
          'Rest': { duration_sec: 180, avg_hr: 72, avg_vo2: 350, avg_rer: 0.82 },
          'Warm-up': { duration_sec: 180, avg_hr: 105, avg_vo2: 1200, avg_rer: 0.85 },
          'Exercise': { duration_sec: 960, avg_hr: 155, avg_vo2: 2800, avg_rer: 0.95 },
          'Peak': { duration_sec: 60, avg_hr: 185, max_hr: 188, avg_vo2: 3800, max_vo2: 3850, avg_rer: 1.12 },
          'Recovery': { duration_sec: 120, avg_hr: 140, avg_vo2: 1500, avg_rer: 1.0 },
        },
        fatmax: {
          fat_max_g_min: 0.68,
          fat_max_hr: 145,
          fat_max_watt: 130,
          fat_max_vo2: 2100,
          fat_max_rer: 0.87,
          fat_max_time_sec: 600,
        },
        vo2max: {
          vo2_max: 3850,
          vo2_max_rel: 52.3,
          vco2_max: 4200,
          hr_max: 188,
          rer_at_max: 1.12,
          vo2_max_time_sec: 1320,
        },
        vt1_hr: 135,
        vt1_vo2: 2100,
        vt2_hr: 165,
        vt2_vo2: 3200,
        timeseries,
        timeseries_interval: interval,
        total_fat_burned_g: 18.5,
        total_cho_burned_g: 45.2,
        avg_rer: 0.95,
        exercise_duration_sec: 960,
        // Processed data (demo)
        processed_series: {
          raw: [
            { power: 80, fat_oxidation: 0.35, cho_oxidation: 0.22 },
            { power: 100, fat_oxidation: 0.52, cho_oxidation: 0.35 },
            { power: 120, fat_oxidation: 0.65, cho_oxidation: 0.48 },
            { power: 140, fat_oxidation: 0.68, cho_oxidation: 0.62 },
            { power: 160, fat_oxidation: 0.58, cho_oxidation: 0.85 },
            { power: 180, fat_oxidation: 0.42, cho_oxidation: 1.15 },
            { power: 200, fat_oxidation: 0.28, cho_oxidation: 1.52 },
            { power: 220, fat_oxidation: 0.15, cho_oxidation: 1.95 },
            { power: 240, fat_oxidation: 0.08, cho_oxidation: 2.35 },
          ],
          binned: [
            { power: 80, fat_oxidation: 0.35, cho_oxidation: 0.22, count: 12 },
            { power: 100, fat_oxidation: 0.52, cho_oxidation: 0.35, count: 15 },
            { power: 120, fat_oxidation: 0.65, cho_oxidation: 0.48, count: 18 },
            { power: 140, fat_oxidation: 0.68, cho_oxidation: 0.62, count: 20 },
            { power: 160, fat_oxidation: 0.58, cho_oxidation: 0.85, count: 22 },
            { power: 180, fat_oxidation: 0.42, cho_oxidation: 1.15, count: 18 },
            { power: 200, fat_oxidation: 0.28, cho_oxidation: 1.52, count: 15 },
            { power: 220, fat_oxidation: 0.15, cho_oxidation: 1.95, count: 10 },
            { power: 240, fat_oxidation: 0.08, cho_oxidation: 2.35, count: 5 },
          ],
          smoothed: [
            { power: 80, fat_oxidation: 0.36, cho_oxidation: 0.21 },
            { power: 100, fat_oxidation: 0.51, cho_oxidation: 0.34 },
            { power: 120, fat_oxidation: 0.64, cho_oxidation: 0.49 },
            { power: 140, fat_oxidation: 0.67, cho_oxidation: 0.63 },
            { power: 160, fat_oxidation: 0.57, cho_oxidation: 0.86 },
            { power: 180, fat_oxidation: 0.41, cho_oxidation: 1.16 },
            { power: 200, fat_oxidation: 0.27, cho_oxidation: 1.53 },
            { power: 220, fat_oxidation: 0.14, cho_oxidation: 1.96 },
            { power: 240, fat_oxidation: 0.07, cho_oxidation: 2.36 },
          ],
        },
        metabolic_markers: {
          fat_max: {
            power: 140,
            mfo: 0.68,
            zone_min: 120,
            zone_max: 160,
          },
          crossover: {
            power: 165,
            fat_value: 0.55,
            cho_value: 0.55,
          },
        },
      };
    }
    const response = await client.get(`/tests/${testId}/analysis`, {
      params: { interval, include_processed, loess_frac, bin_size, aggregation_method }
    });
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
