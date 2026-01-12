import { projectId, publicAnonKey } from '/utils/supabase/info';
import { createClient } from '@supabase/supabase-js';
import { sampleTestData, sampleSubjects } from './sampleData';

const API_BASE = `https://${projectId}.supabase.co/functions/v1/make-server-3f6fd63f`;

// Initialize Supabase client for frontend auth
export const supabase = createClient(
  `https://${projectId}.supabase.co`,
  publicAnonKey
);

// Check if we're in demo mode
function isDemoMode() {
  return localStorage.getItem('demoMode') === 'true';
}

// Helper to get auth header
async function getAuthHeader() {
  if (isDemoMode()) {
    return `Bearer ${publicAnonKey}`;
  }
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token ? `Bearer ${session.access_token}` : `Bearer ${publicAnonKey}`;
}

// API Functions
export const api = {
  // Auth
  async signIn(email: string, password: string) {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data;
  },

  async signOut() {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  },

  async getSession() {
    const { data: { session } } = await supabase.auth.getSession();
    return session;
  },

  async signUp(email: string, password: string, name: string, role: string, subjectInfo?: any) {
    const response = await fetch(`${API_BASE}/auth/signup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': await getAuthHeader(),
      },
      body: JSON.stringify({ email, password, name, role, subjectInfo }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Signup failed');
    return data;
  },

  async getCurrentUser() {
    const response = await fetch(`${API_BASE}/auth/me`, {
      headers: {
        'Authorization': await getAuthHeader(),
      },
    });

    if (!response.ok) throw new Error('Not authenticated');
    return response.json();
  },

  // Subjects
  async getSubjects() {
    if (isDemoMode()) {
      return sampleSubjects;
    }
    const response = await fetch(`${API_BASE}/subjects`, {
      headers: {
        'Authorization': await getAuthHeader(),
      },
    });
    return response.json();
  },

  async getSubject(id: string) {
    if (isDemoMode()) {
      return sampleSubjects.find(s => s.id === id) || sampleSubjects[0];
    }
    const response = await fetch(`${API_BASE}/subjects/${id}`, {
      headers: {
        'Authorization': await getAuthHeader(),
      },
    });
    return response.json();
  },

  async createSubject(subjectData: any) {
    if (isDemoMode()) {
      return { success: true, subject: subjectData };
    }
    const response = await fetch(`${API_BASE}/subjects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': await getAuthHeader(),
      },
      body: JSON.stringify(subjectData),
    });
    return response.json();
  },

  // Tests
  async getTests() {
    if (isDemoMode()) {
      return [sampleTestData];
    }
    const response = await fetch(`${API_BASE}/tests`, {
      headers: {
        'Authorization': await getAuthHeader(),
      },
    });
    return response.json();
  },

  async getTest(id: string) {
    if (isDemoMode()) {
      return sampleTestData;
    }
    const response = await fetch(`${API_BASE}/tests/${id}`, {
      headers: {
        'Authorization': await getAuthHeader(),
      },
    });
    return response.json();
  },

  async createTest(testData: any) {
    const response = await fetch(`${API_BASE}/tests`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': await getAuthHeader(),
      },
      body: JSON.stringify(testData),
    });
    return response.json();
  },

  async updateTest(id: string, updates: any) {
    const response = await fetch(`${API_BASE}/tests/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': await getAuthHeader(),
      },
      body: JSON.stringify(updates),
    });
    return response.json();
  },

  async deleteTest(id: string) {
    const response = await fetch(`${API_BASE}/tests/${id}`, {
      method: 'DELETE',
      headers: {
        'Authorization': await getAuthHeader(),
      },
    });
    return response.json();
  },

  // Cohort Analysis
  async getCohortStats(filters: any) {
    const response = await fetch(`${API_BASE}/cohort/stats`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': await getAuthHeader(),
      },
      body: JSON.stringify({ filters }),
    });
    return response.json();
  },
};