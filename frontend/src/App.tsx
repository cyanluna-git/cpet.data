import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider, useAuth, type User } from '@/hooks/useAuth';
import { useNavigation } from '@/hooks/useNavigation';
import { toast, Toaster } from 'sonner';
import { ReactNode } from 'react';

// Pages
import { LoginPage } from '@/components/pages/LoginPage';
import { ResearcherDashboard } from '@/components/pages/ResearcherDashboard';
import { SubjectDashboard } from '@/components/pages/SubjectDashboard';
import { SubjectListPage } from '@/components/pages/SubjectListPage';
import { SubjectDetailPage } from '@/components/pages/SubjectDetailPage';
import { SingleTestView } from '@/components/pages/SingleTestView';
import { CohortAnalysisPage } from '@/components/pages/CohortAnalysisPage';
import { MetabolismPage } from '@/components/pages/MetabolismPage';

// Styles
import '@/styles/index.css';
import '@/styles/tailwind.css';
import '@/styles/theme.css';

// Loading Spinner
function LoadingSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-gray-600">로딩중...</p>
      </div>
    </div>
  );
}

// Protected Route Component
interface ProtectedRouteProps {
  children: ReactNode;
  allowedRoles?: Array<'admin' | 'researcher' | 'subject'>;
}

function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { user, loading } = useAuth();

  if (loading) return <LoadingSpinner />;
  if (!user) return <Navigate to="/login" />;
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" />;
  }

  return <>{children}</>;
}

// Wrapper components to adapt legacy props to React Router
function LoginPageWrapper() {
  const { handleNavigate } = useNavigation();
  const { login, demoLogin } = useAuth();

  async function handleLoginSubmit(email: string, password: string) {
    try {
      await login(email, password);
      toast.success('로그인 성공');
      handleNavigate('researcher-dashboard');
    } catch (error: any) {
      toast.error(error.message || '로그인 실패');
      throw error;
    }
  }

  function handleDemoLoginSubmit(role: 'researcher' | 'subject') {
    demoLogin(role);
    toast.success('데모 모드로 접속했습니다');
    if (role === 'subject') {
      handleNavigate('subject-dashboard');
    } else {
      handleNavigate('researcher-dashboard');
    }
  }

  return <LoginPage onLogin={handleLoginSubmit} onDemoLogin={handleDemoLoginSubmit} />;
}

function ResearcherDashboardWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('researcher-dashboard');
  }

  return (
    <ResearcherDashboard
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function SubjectDashboardWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('subject-dashboard');
  }

  return (
    <SubjectDashboard
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function SubjectListWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('subject-list');
  }

  return (
    <SubjectListPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function SubjectDetailWrapper() {
  const { id } = useParams<{ id: string }>();
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('subject-detail', { subjectId: id });
  }

  return (
    <SubjectDetailPage
      user={user as User}
      subjectId={id!}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function SingleTestViewWrapper() {
  const { id } = useParams<{ id: string }>();
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('test-view', { testId: id });
  }

  return (
    <SingleTestView
      user={user as User}
      testId={id!}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function CohortAnalysisWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('cohort-analysis');
  }

  return (
    <CohortAnalysisPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function MetabolismWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    handleNavigate('metabolism');
  }

  return (
    <MetabolismPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

// Root redirect based on user role
function RootRedirect() {
  const { user, loading } = useAuth();

  if (loading) return <LoadingSpinner />;
  if (!user) return <Navigate to="/login" />;

  if (user.role === 'subject') {
    return <Navigate to="/my-dashboard" />;
  }
  return <ResearcherDashboardWrapper />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors />
        <Routes>
          <Route path="/login" element={<LoginPageWrapper />} />

          {/* Root - redirects based on role */}
          <Route path="/" element={
            <ProtectedRoute>
              <RootRedirect />
            </ProtectedRoute>
          } />

          {/* Researcher routes */}
          <Route path="/subjects" element={
            <ProtectedRoute allowedRoles={['admin', 'researcher']}>
              <SubjectListWrapper />
            </ProtectedRoute>
          } />

          <Route path="/subjects/:id" element={
            <ProtectedRoute allowedRoles={['admin', 'researcher']}>
              <SubjectDetailWrapper />
            </ProtectedRoute>
          } />

          <Route path="/cohort" element={
            <ProtectedRoute>
              <CohortAnalysisWrapper />
            </ProtectedRoute>
          } />

          {/* Subject routes */}
          <Route path="/my-dashboard" element={
            <ProtectedRoute>
              <SubjectDashboardWrapper />
            </ProtectedRoute>
          } />

          {/* Shared routes */}
          <Route path="/tests/:id" element={
            <ProtectedRoute>
              <SingleTestViewWrapper />
            </ProtectedRoute>
          } />

          <Route path="/metabolism" element={
            <ProtectedRoute>
              <MetabolismWrapper />
            </ProtectedRoute>
          } />

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
