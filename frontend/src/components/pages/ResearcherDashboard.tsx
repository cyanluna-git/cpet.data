import { useState, useEffect } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Upload, Users, FileText, TrendingUp, Activity, Calendar } from 'lucide-react';
import { api } from '@/lib/api';
import { extractItems, getErrorMessage } from '@/utils/apiHelpers';
import { sampleTestData, sampleSubjects } from '@/utils/sampleData';
import { toast } from 'sonner';

interface ResearcherDashboardProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

export function ResearcherDashboard({ user, onLogout, onNavigate }: ResearcherDashboardProps) {
  const [tests, setTests] = useState<any[]>([]);
  const [subjects, setSubjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [testsResponse, subjectsResponse] = await Promise.all([
        api.getTests(),
        api.getSubjects()
      ]);

      // Extract items from paginated responses
      const testsData = extractItems(testsResponse);
      const subjectsData = extractItems(subjectsResponse);

      // If no data exists, create sample data
      if (testsData.length === 0) {
        await initializeSampleData();
      } else {
        setTests(testsData);
        setSubjects(subjectsData);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function initializeSampleData() {
    try {
      // Create sample subjects
      const createdSubjects = [];
      for (const subject of sampleSubjects) {
        const created = await api.createSubject(subject);
        createdSubjects.push(created);
      }

      // Create sample test
      const testData = {
        ...sampleTestData,
        subject_id: createdSubjects[0].id
      };
      const createdTest = await api.createTest(testData);

      setSubjects(createdSubjects);
      setTests([createdTest]);
      toast.success('샘플 데이터가 생성되었습니다');
    } catch (error) {
      console.error('Failed to initialize sample data:', error);
      toast.error('샘플 데이터 생성 실패');
    }
  }

  const stats = {
    totalSubjects: subjects.length,
    totalTests: tests.length,
    recentTests: tests.filter(t => {
      const testDate = new Date(t.test_date);
      const monthAgo = new Date();
      monthAgo.setMonth(monthAgo.getMonth() - 1);
      return testDate > monthAgo;
    }).length
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navigation user={user} currentView="researcher-dashboard" onNavigate={onNavigate} onLogout={onLogout} />
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-gray-600">데이터 로딩 중...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="researcher-dashboard" onNavigate={onNavigate} onLogout={onLogout} />
      
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Welcome Section */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            안녕하세요, {user.name}님 👋
          </h1>
          <p className="text-gray-600">
            오늘도 좋은 연구 되세요. 최근 활동과 주요 지표를 확인하세요.
          </p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <Button
            size="lg"
            className="h-20 bg-[#2563EB] hover:bg-[#1d4ed8] gap-3 text-lg"
            onClick={() => toast.info('업로드 기능은 곧 추가됩니다')}
          >
            <Upload className="w-6 h-6" />
            <span>새 테스트 업로드</span>
          </Button>
          
          <Button
            size="lg"
            variant="outline"
            className="h-20 gap-3 text-lg border-2 border-[#2563EB] text-[#2563EB] hover:bg-[#2563EB] hover:text-white"
            onClick={() => onNavigate('subject-list')}
          >
            <Users className="w-6 h-6" />
            <span>피험자 관리</span>
          </Button>
        </div>

        {/* Statistics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="border-t-4 border-t-[#2563EB]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
                <Users className="w-4 h-4" />
                총 피험자 수
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-gray-900">{stats.totalSubjects}</div>
              <p className="text-xs text-gray-500 mt-1">등록된 피험자</p>
            </CardContent>
          </Card>

          <Card className="border-t-4 border-t-[#10B981]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
                <FileText className="w-4 h-4" />
                전체 테스트 수
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-gray-900">{stats.totalTests}</div>
              <p className="text-xs text-gray-500 mt-1">완료된 검사</p>
            </CardContent>
          </Card>

          <Card className="border-t-4 border-t-[#F97316]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                이번 달 테스트
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-gray-900">{stats.recentTests}</div>
              <p className="text-xs text-gray-500 mt-1">최근 30일</p>
            </CardContent>
          </Card>
        </div>

        {/* Recent Tests */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-900">최근 업로드된 테스트</h2>
            <Button variant="ghost" onClick={() => onNavigate('subject-list')}>
              전체 보기 →
            </Button>
          </div>

          {tests.length === 0 ? (
            <Card className="p-12 text-center">
              <Activity className="w-16 h-16 text-gray-300 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-gray-900 mb-2">아직 테스트가 없습니다</h3>
              <p className="text-gray-600 mb-6">첫 번째 CPET 테스트를 업로드하여 시작하세요.</p>
              <Button className="bg-[#2563EB]" onClick={() => toast.info('업로드 기능은 곧 추가됩니다')}>
                <Upload className="w-4 h-4 mr-2" />
                테스트 업로드
              </Button>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {tests.slice(0, 6).filter(test => test && test.id).map((test) => (
                <Card
                  key={test.id}
                  className="hover:shadow-lg transition-shadow cursor-pointer"
                  onClick={() => onNavigate('test-view', { testId: test.id })}
                >
                  <CardHeader>
                    <CardTitle className="text-base flex items-center justify-between">
                      <span className="truncate">{test.metadata?.research_id || test.subject_id.slice(0, 8)}</span>
                      <Activity className="w-5 h-5 text-[#2563EB]" />
                    </CardTitle>
                    <CardDescription className="flex items-center gap-2 text-xs">
                      <Calendar className="w-3 h-3" />
                      {new Date(test.test_date).toLocaleDateString('ko-KR')}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-gray-500 text-xs">VO2 MAX</p>
                        <p className="font-bold text-[#3B82F6]">
                          {test.summary?.vo2_max_rel?.toFixed(1) || 'N/A'} <span className="text-xs font-normal">mL/kg/min</span>
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-500 text-xs">HR MAX</p>
                        <p className="font-bold text-[#EF4444]">
                          {test.summary?.hr_max || 'N/A'} <span className="text-xs font-normal">bpm</span>
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-500 text-xs">FATMAX</p>
                        <p className="font-bold text-[#10B981]">
                          {test.summary?.fat_max_hr || 'N/A'} <span className="text-xs font-normal">bpm</span>
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-500 text-xs">프로토콜</p>
                        <p className="font-semibold">{test.protocol_type || 'BxB'}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Managed Subjects Section */}
        {subjects.length > 0 && (
          <div className="mt-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-900">관리 중인 피험자</h2>
              <Button variant="ghost" onClick={() => onNavigate('subject-list')}>
                전체 보기 →
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {subjects.slice(0, 6).filter(subject => subject && subject.id).map((subject) => (
                <Card
                  key={subject.id}
                  className="hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => onNavigate('subject-detail', { subjectId: subject.id })}
                >
                  <CardContent className="pt-6">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-gradient-to-br from-[#2563EB] to-[#3B82F6] rounded-full flex items-center justify-center text-white font-bold text-lg">
                        {subject.name?.charAt(0) || subject.research_id?.charAt(0)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-gray-900 truncate">{subject.research_id}</h3>
                        <p className="text-sm text-gray-500">
                          {subject.gender === 'M' ? '남성' : '여성'} · {new Date().getFullYear() - subject.birth_year}세
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}