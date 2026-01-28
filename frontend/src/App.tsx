import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider, useAuth, type User } from '@/hooks/useAuth';
import { useNavigation } from '@/hooks/useNavigation';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { toast, Toaster } from 'sonner';
import { lazy, Suspense, type ReactNode } from 'react';

// Static imports - needed immediately
import { LoginPage } from '@/components/pages/LoginPage';

// Lazy loaded pages - loaded on demand (bundle-dynamic-imports)
const ResearcherDashboard = lazy(() => import('@/components/pages/ResearcherDashboard').then(m => ({ default: m.ResearcherDashboard })));
const SubjectDashboard = lazy(() => import('@/components/pages/SubjectDashboard').then(m => ({ default: m.SubjectDashboard })));
const SubjectListPage = lazy(() => import('@/components/pages/SubjectListPage').then(m => ({ default: m.SubjectListPage })));
const SubjectDetailPage = lazy(() => import('@/components/pages/SubjectDetailPage').then(m => ({ default: m.SubjectDetailPage })));
const SingleTestView = lazy(() => import('@/components/pages/SingleTestView').then(m => ({ default: m.SingleTestView })));
const CohortAnalysisPage = lazy(() => import('@/components/pages/CohortAnalysisPage').then(m => ({ default: m.CohortAnalysisPage })));
const MetabolismPage = lazy(() => import('@/components/pages/MetabolismPage').then(m => ({ default: m.MetabolismPage })));
const AdminDashboardPage = lazy(() => import('@/components/pages/AdminDashboardPage').then(m => ({ default: m.AdminDashboardPage })));
const AdminUsersPage = lazy(() => import('@/components/pages/AdminUsersPage').then(m => ({ default: m.AdminUsersPage })));
const AdminDataPage = lazy(() => import('@/components/pages/AdminDataPage').then(m => ({ default: m.AdminDataPage })));
const RawDataViewerPage = lazy(() => import('@/components/pages/RawDataViewerPage').then(m => ({ default: m.RawDataViewerPage })));

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

  function handleDemoLogin(role: 'researcher' | 'subject') {
    demoLogin(role);
    toast.success(`${role === 'researcher' ? '연구자' : '피험자'} 데모 로그인`);
    if (role === 'researcher') {
      handleNavigate('researcher-dashboard');
    } else {
      handleNavigate('subject-dashboard');
    }
  }

  return <LoginPage onLogin={handleLoginSubmit} onDemoLogin={handleDemoLogin} />;
}

function ResearcherDashboardWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    window.location.href = '/login';
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
    window.location.href = '/login';
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
    window.location.href = '/login';
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
    window.location.href = '/login';
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
    window.location.href = '/login';
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
    window.location.href = '/login';
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
    window.location.href = '/login';
  }

  return (
    <MetabolismPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function AdminDashboardWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    window.location.href = '/login';
  }

  return (
    <AdminDashboardPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function AdminUsersWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    window.location.href = '/login';
  }

  return (
    <AdminUsersPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function AdminDataWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    window.location.href = '/login';
  }

  return (
    <AdminDataPage
      user={user as User}
      onLogout={handleLogout}
      onNavigate={handleNavigate}
    />
  );
}

function RawDataViewerWrapper() {
  const { handleNavigate } = useNavigation();
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    toast.success('로그아웃 되었습니다');
    window.location.href = '/login';
  }

  return (
    <RawDataViewerPage
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

  if (user.role === 'admin') {
    return <Navigate to="/admin" />;
  }

  if (user.role === 'subject') {
    return <Navigate to="/my-dashboard" />;
  }
  return <ResearcherDashboardWrapper />;
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Toaster position="top-right" richColors />
          <Suspense fallback={<LoadingSpinner />}>
          <Routes>
            <Route path="/login" element={<LoginPageWrapper />} />

            {/* Root - redirects based on role */}
            <Route path="/" element={
              <ProtectedRoute>
                <RootRedirect />
              </ProtectedRoute>
            } />

            {/* Researcher routes */}
            {/* Admin routes */}
            <Route path="/admin" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <AdminDashboardWrapper />
              </ProtectedRoute>
            } />

            <Route path="/admin/users" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <AdminUsersWrapper />
              </ProtectedRoute>
            } />

            <Route path="/admin/data" element={
              <ProtectedRoute allowedRoles={['admin']}>
                <AdminDataWrapper />
              </ProtectedRoute>
            } />

            <Route path="/raw-data" element={
              <ProtectedRoute allowedRoles={['admin', 'researcher']}>
                <RawDataViewerWrapper />
              </ProtectedRoute>
            } />

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
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
