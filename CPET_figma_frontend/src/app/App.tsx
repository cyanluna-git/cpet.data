import { useState, useEffect } from 'react';
import { api } from './utils/api';
import { LoginPage } from './components/LoginPage';
import { ResearcherDashboard } from './components/ResearcherDashboard';
import { SubjectDashboard } from './components/SubjectDashboard';
import { SingleTestView } from './components/SingleTestView';
import { SubjectListPage } from './components/SubjectListPage';
import { SubjectDetailPage } from './components/SubjectDetailPage';
import { CohortAnalysisPage } from './components/CohortAnalysisPage';
import { MetabolismPage } from './components/MetabolismPage';
import { toast, Toaster } from 'sonner';

type View = 'login' | 'researcher-dashboard' | 'subject-dashboard' | 'test-view' | 'subject-list' | 'subject-detail' | 'cohort-analysis' | 'metabolism';

interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'researcher' | 'subject';
}

export default function App() {
  const [currentView, setCurrentView] = useState<View>('login');
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const session = await api.getSession();
      if (session) {
        const userData = await api.getCurrentUser();
        setUser(userData);
        
        // Route to appropriate dashboard based on role
        if (userData.role === 'subject') {
          setCurrentView('subject-dashboard');
        } else {
          setCurrentView('researcher-dashboard');
        }
      }
    } catch (error) {
      console.log('Not authenticated');
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(email: string, password: string) {
    try {
      await api.signIn(email, password);
      const userData = await api.getCurrentUser();
      setUser(userData);
      setDemoMode(false);
      
      // Route to appropriate dashboard
      if (userData.role === 'subject') {
        setCurrentView('subject-dashboard');
      } else {
        setCurrentView('researcher-dashboard');
      }
      
      toast.success('로그인 성공');
    } catch (error: any) {
      toast.error(error.message || '로그인 실패');
      throw error;
    }
  }

  function handleDemoLogin(role: 'researcher' | 'subject') {
    // Create demo user without backend authentication
    const demoUsers = {
      researcher: {
        id: 'demo-researcher-1',
        email: 'demo@researcher.com',
        name: '연구자 데모',
        role: 'researcher' as const,
      },
      subject: {
        id: '660e8400-e29b-41d4-a716-446655440001', // Use actual subject ID from sampleSubjects
        email: 'demo@subject.com',
        name: '박용두', // Use actual subject name
        role: 'subject' as const,
      }
    };

    const demoUser = demoUsers[role];
    setUser(demoUser);
    setDemoMode(true);
    localStorage.setItem('demoMode', 'true');
    
    // Route to appropriate dashboard
    if (role === 'subject') {
      setCurrentView('subject-dashboard');
    } else {
      setCurrentView('researcher-dashboard');
    }
    
    toast.success('데모 모드로 접속했습니다');
  }

  async function handleLogout() {
    try {
      if (!demoMode) {
        await api.signOut();
      }
      setUser(null);
      setDemoMode(false);
      localStorage.removeItem('demoMode');
      setCurrentView('login');
      toast.success('로그아웃 되었습니다');
    } catch (error: any) {
      toast.error(error.message || '로그아웃 실패');
    }
  }

  function navigateTo(view: View, params?: any) {
    if (view === 'test-view' && params?.testId) {
      setSelectedTestId(params.testId);
    }
    if (view === 'subject-detail' && params?.subjectId) {
      setSelectedSubjectId(params.subjectId);
    }
    setCurrentView(view);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">로딩중...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <Toaster position="top-right" richColors />
      
      {currentView === 'login' && (
        <LoginPage onLogin={handleLogin} onDemoLogin={handleDemoLogin} />
      )}

      {currentView === 'researcher-dashboard' && user && (
        <ResearcherDashboard
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}

      {currentView === 'subject-dashboard' && user && (
        <SubjectDashboard
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}

      {currentView === 'subject-list' && user && (
        <SubjectListPage
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}

      {currentView === 'subject-detail' && user && selectedSubjectId && (
        <SubjectDetailPage
          user={user}
          subjectId={selectedSubjectId}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}

      {currentView === 'test-view' && user && selectedTestId && (
        <SingleTestView
          user={user}
          testId={selectedTestId}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}

      {currentView === 'cohort-analysis' && user && (
        <CohortAnalysisPage
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}

      {currentView === 'metabolism' && user && (
        <MetabolismPage
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateTo}
        />
      )}
    </>
  );
}