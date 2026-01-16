import { useEffect, useState } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Database, ExternalLink } from 'lucide-react';
import { api, type AdminStats } from '@/lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '@/utils/apiHelpers';

interface AdminDataPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

export function AdminDataPage({ user, onLogout, onNavigate }: AdminDataPageProps) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      setLoading(true);
      const response = await api.adminGetStats();
      setStats(response);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="admin-data" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Database className="w-6 h-6 text-[#2563EB]" />
              <h1 className="text-3xl font-bold text-gray-900">DB 관리</h1>
            </div>
            <p className="text-gray-600">데이터 현황 확인 및 운영 바로가기</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onNavigate('admin-dashboard')}>대시보드</Button>
            <Button variant="outline" onClick={load}>새로고침</Button>
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
                  <p className="text-3xl font-bold text-gray-900">{stats?.users_total ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">피험자</p>
                  <p className="text-3xl font-bold text-gray-900">{stats?.subjects_total ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">테스트</p>
                  <p className="text-3xl font-bold text-gray-900">{stats?.tests_total ?? 0}</p>
                </CardContent>
              </Card>
            </div>

            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-2">운영 링크</h2>
              <p className="text-sm text-gray-600 mb-4">기존 기능(피험자/테스트/분석)으로 바로 이동합니다.</p>
              <div className="flex gap-2 flex-wrap">
                <Button variant="outline" className="gap-2" onClick={() => onNavigate('subject-list')}>
                  피험자 관리
                  <ExternalLink className="w-4 h-4" />
                </Button>
                <Button variant="outline" className="gap-2" onClick={() => onNavigate('cohort-analysis')}>
                  코호트 분석
                  <ExternalLink className="w-4 h-4" />
                </Button>
                <Button variant="outline" className="gap-2" onClick={() => onNavigate('metabolism')}>
                  메타볼리즘
                  <ExternalLink className="w-4 h-4" />
                </Button>
              </div>
            </Card>

            <Card className="p-6 mt-6 border-red-200">
              <h2 className="text-lg font-semibold text-red-700 mb-2">Danger Zone</h2>
              <p className="text-sm text-gray-600">
                데이터 삭제/초기화 같은 위험 작업은 아직 UI로 제공하지 않습니다. 필요하면 요구사항에 맞춰
                개발환경 전용(예: DEBUG=true)으로 안전장치(confirm string) 포함해서 추가할 수 있어요.
              </p>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
