import { useEffect, useState } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Shield, Users, Database } from 'lucide-react';
import { api, type AdminStats } from '@/lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '@/utils/apiHelpers';

interface AdminDashboardPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

export function AdminDashboardPage({ user, onLogout, onNavigate }: AdminDashboardPageProps) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  async function loadStats() {
    try {
      setLoading(true);
      const response = await api.adminGetStats();
      setStats(response);
    } catch (error) {
      console.error('Failed to load admin stats:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="admin-dashboard" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-6 h-6 text-[#2563EB]" />
              <h1 className="text-2xl md:text-3xl font-bold text-gray-900">슈퍼어드민</h1>
            </div>
            <p className="text-gray-600">회원/권한 관리 및 운영 도구</p>
          </div>

          <div className="flex gap-2">
            <Button variant="outline" onClick={loadStats}>
              새로고침
            </Button>
            <Button className="bg-[#2563EB] gap-2" onClick={() => onNavigate('admin-users')}>
              <Users className="w-4 h-4" />
              사용자 관리
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">전체 사용자</p>
                  <p className="text-xl sm:text-2xl md:text-3xl font-bold text-gray-900">{stats?.users_total ?? 0}</p>
                  <p className="text-xs text-gray-500 mt-2">활성 {stats?.users_active ?? 0} / 비활성 {stats?.users_inactive ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">피험자 수</p>
                  <p className="text-xl sm:text-2xl md:text-3xl font-bold text-gray-900">{stats?.subjects_total ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">테스트 수</p>
                  <p className="text-xl sm:text-2xl md:text-3xl font-bold text-gray-900">{stats?.tests_total ?? 0}</p>
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 mb-1">회원/역할 관리</h2>
                    <p className="text-sm text-gray-600">사용자 생성/수정/비활성화 및 역할 변경</p>
                  </div>
                  <Users className="w-6 h-6 text-gray-400" />
                </div>
                <div className="mt-4">
                  <Button className="bg-[#2563EB]" onClick={() => onNavigate('admin-users')}>
                    사용자 관리 열기
                  </Button>
                </div>
              </Card>

              <Card className="p-6">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 mb-1">데이터/DB 상태</h2>
                    <p className="text-sm text-gray-600">데이터 현황 확인 및 운영 링크</p>
                  </div>
                  <Database className="w-6 h-6 text-gray-400" />
                </div>
                <div className="mt-4 flex gap-2 flex-wrap">
                  <Button variant="outline" onClick={() => onNavigate('admin-data')}>DB 도구</Button>
                  <Button variant="outline" onClick={() => onNavigate('subject-list')}>피험자</Button>
                </div>
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
