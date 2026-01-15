import { BrowserRouter, Routes, Route, Navigate, useNavigate, useParams } from 'react-router-dom';
import { AuthProvider, useAuth, type User } from '@/hooks/useAuth';
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
type View = 'login' | 'researcher-dashboard' | 'subject-dashboard' | 'test-view' | 'subject-list' | 'subject-detail' | 'cohort-analysis' | 'metabolism';

function LoginPageWrapper() {
  const navigate = useNavigate();
  const { login, demoLogin } = useAuth();

  async function handleLogin(email: string, password: string) {
    try {
      await login(email, password);
      toast.success('로그인 성공');
      navigate('/');
    } catch (error: any) {
      toast.error(error.message || '로그인 실패');
      throw error;
    }
  }

  function handleDemoLogin(role: 'researcher' | 'subject') {
    demoLogin(role);
    toast.success('데모 모드로 접속했습니다');
    if (role === 'subject') {
      navigate('/my-dashboard');
    } else {
      navigate('/');
    }
  }

  return <LoginPage onLogin={handleLogin} onDemoLogin={handleDemoLogin} />;
}

function ResearcherDashboardWrapper() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View, params?: { testId?: string; subjectId?: string }) {
    switch (view) {
      case 'test-view':
        navigate(`/tests/${params?.testId}`);
        break;
      case 'subject-detail':
        navigate(`/subjects/${params?.subjectId}`);
        break;
      case 'subject-list':
        navigate('/subjects');
        break;
      case 'cohort-analysis':
        navigate('/cohort');
        break;
      case 'metabolism':
        navigate('/metabolism');
        break;
      default:
        navigate('/');
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View, params?: { testId?: string }) {
    switch (view) {
      case 'test-view':
        navigate(`/tests/${params?.testId}`);
        break;
      case 'cohort-analysis':
        navigate('/cohort');
        break;
      case 'metabolism':
        navigate('/metabolism');
        break;
      default:
        navigate('/my-dashboard');
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View, params?: { subjectId?: string }) {
    switch (view) {
      case 'subject-detail':
        navigate(`/subjects/${params?.subjectId}`);
        break;
      case 'researcher-dashboard':
        navigate('/');
        break;
      case 'cohort-analysis':
        navigate('/cohort');
        break;
      case 'metabolism':
        navigate('/metabolism');
        break;
      default:
        navigate('/subjects');
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View, params?: { testId?: string; subjectId?: string }) {
    switch (view) {
      case 'test-view':
        navigate(`/tests/${params?.testId}`);
        break;
      case 'subject-list':
        navigate('/subjects');
        break;
      case 'researcher-dashboard':
        navigate('/');
        break;
      case 'cohort-analysis':
        navigate('/cohort');
        break;
      case 'metabolism':
        navigate('/metabolism');
        break;
      default:
        navigate(`/subjects/${id}`);
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View, params?: { subjectId?: string }) {
    switch (view) {
      case 'subject-detail':
        navigate(`/subjects/${params?.subjectId}`);
        break;
      case 'subject-list':
        navigate('/subjects');
        break;
      case 'researcher-dashboard':
        navigate('/');
        break;
      case 'cohort-analysis':
        navigate('/cohort');
        break;
      case 'metabolism':
        navigate('/metabolism');
        break;
      default:
        navigate(`/tests/${id}`);
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View) {
    switch (view) {
      case 'researcher-dashboard':
        navigate('/');
        break;
      case 'subject-list':
        navigate('/subjects');
        break;
      case 'metabolism':
        navigate('/metabolism');
        break;
      default:
        navigate('/cohort');
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  function handleNavigate(view: View) {
    switch (view) {
      case 'researcher-dashboard':
        navigate('/');
        break;
      case 'subject-dashboard':
        navigate('/my-dashboard');
        break;
      case 'cohort-analysis':
        navigate('/cohort');
        break;
      default:
        navigate('/metabolism');
    }
  }

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    navigate('/login');
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
