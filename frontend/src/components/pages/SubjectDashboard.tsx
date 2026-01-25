import { useState, useEffect } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Activity, TrendingUp, Heart, Flame, Calendar } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { extractItems, getErrorMessage } from '@/utils/apiHelpers';

interface SubjectDashboardProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

export function SubjectDashboard({ user, onLogout, onNavigate }: SubjectDashboardProps) {
  const [subject, setSubject] = useState<any>(null);
  const [tests, setTests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      // 일반 유저는 본인 테스트만 조회됨 (백엔드에서 subject role 자동 필터링)
      const testsResponse = await api.getTests();
      const testsData = extractItems<any>(testsResponse);
      setTests(testsData);

      // subject 정보는 첫 번째 테스트에서 추출 (있는 경우)
      if (testsData.length > 0 && testsData[0].subject_id) {
        setSubject({ id: testsData[0].subject_id });
      }
    } catch (error) {
      console.error('Failed to load data:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navigation user={user} currentView="subject-dashboard" onNavigate={onNavigate} onLogout={onLogout} />
        <div className="flex items-center justify-center h-96">
          <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
        </div>
      </div>
    );
  }

  const latestTest = tests[0];
  const vo2maxPercentile = latestTest ? 65 : null; // Mock percentile

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="subject-dashboard" onNavigate={onNavigate} onLogout={onLogout} />
      
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Welcome */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            내 대사 프로파일
          </h1>
          <p className="text-gray-600">
            최근 운동 능력 검사 결과와 코호트 비교 분석을 확인하세요.
          </p>
        </div>

        {!latestTest ? (
          <Card className="p-12 text-center">
            <Activity className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">아직 테스트 기록이 없습니다</h3>
            <p className="text-gray-600">첫 번째 CPET 검사를 받으시면 결과가 여기에 표시됩니다.</p>
          </Card>
        ) : (
          <>
            {/* Latest Test Results - Hero Section */}
            <Card className="mb-8 border-t-4 border-t-[#2563EB] bg-gradient-to-br from-blue-50 to-white">
              <CardHeader>
                <CardTitle className="text-xl">최신 검사 결과</CardTitle>
                <CardDescription className="flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  {new Date(latestTest.test_date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-white rounded-lg p-6 shadow-sm">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-12 h-12 bg-[#3B82F6] bg-opacity-10 rounded-full flex items-center justify-center">
                        <Activity className="w-6 h-6 text-[#3B82F6]" />
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">VO2 MAX</p>
                        <p className="text-2xl font-bold text-[#3B82F6]">
                          {latestTest.summary?.vo2_max_rel?.toFixed(1)}
                        </p>
                        <p className="text-xs text-gray-500">mL/kg/min</p>
                      </div>
                    </div>
                    {vo2maxPercentile && (
                      <div className="mt-4 pt-4 border-t">
                        <p className="text-sm text-gray-600 mb-2">코호트 비교</p>
                        <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
                          상위 {100 - vo2maxPercentile}% (우수)
                        </Badge>
                      </div>
                    )}
                  </div>

                  <div className="bg-white rounded-lg p-6 shadow-sm">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-12 h-12 bg-[#EF4444] bg-opacity-10 rounded-full flex items-center justify-center">
                        <Heart className="w-6 h-6 text-[#EF4444]" />
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">최대 심박수</p>
                        <p className="text-2xl font-bold text-[#EF4444]">
                          {latestTest.summary?.hr_max}
                        </p>
                        <p className="text-xs text-gray-500">bpm</p>
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <p className="text-sm text-gray-600">예측치 대비</p>
                      <p className="text-lg font-semibold text-gray-900">
                        {latestTest.summary?.hr_max_percent_pred?.toFixed(0)}%
                      </p>
                    </div>
                  </div>

                  <div className="bg-white rounded-lg p-6 shadow-sm">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-12 h-12 bg-[#10B981] bg-opacity-10 rounded-full flex items-center justify-center">
                        <Flame className="w-6 h-6 text-[#10B981]" />
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">FATMAX 심박수</p>
                        <p className="text-2xl font-bold text-[#10B981]">
                          {latestTest.summary?.fat_max_hr}
                        </p>
                        <p className="text-xs text-gray-500">bpm</p>
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <p className="text-sm text-gray-600">지방 연소 최대 심박수</p>
                      <p className="text-xs text-gray-500 mt-1">
                        운동 강도: {latestTest.summary?.fat_max_watt}W
                      </p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* What This Means */}
            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-[#2563EB]" />
                  이 결과가 의미하는 것
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
                  <h4 className="font-semibold text-gray-900 mb-2">💪 당신의 유산소 능력</h4>
                  <p className="text-sm text-gray-700">
                    VO2 MAX {latestTest.summary?.vo2_max_rel?.toFixed(1)} mL/kg/min는 
                    {' '}{latestTest.metadata?.age || 50}세 {latestTest.metadata?.gender === 'M' ? '남성' : '여성'} 평균보다 
                    <span className="font-semibold text-[#2563EB]"> 우수한 수준</span>입니다.
                  </p>
                </div>

                <div className="p-4 bg-green-50 rounded-lg border border-green-100">
                  <h4 className="font-semibold text-gray-900 mb-2">🔥 지방 연소 최적 구간</h4>
                  <p className="text-sm text-gray-700">
                    당신의 지방 연소는 심박수 <span className="font-semibold text-[#10B981]">{latestTest.summary?.fat_max_hr} bpm</span>에서 
                    가장 효율적입니다. 체중 감량 운동 시 이 심박수를 유지하면 최대 효과를 얻을 수 있습니다.
                  </p>
                </div>

                <div className="p-4 bg-orange-50 rounded-lg border border-orange-100">
                  <h4 className="font-semibold text-gray-900 mb-2">🎯 추천 운동 강도</h4>
                  <p className="text-sm text-gray-700">
                    유산소 운동: 심박수 {Math.floor((latestTest.summary?.fat_max_hr || 145) * 0.85)}-{latestTest.summary?.fat_max_hr} bpm (가벼운 달리기, 사이클링)
                    <br />
                    고강도 훈련: 심박수 {Math.floor((latestTest.summary?.hr_max || 185) * 0.85)}-{latestTest.summary?.hr_max} bpm (인터벌 트레이닝)
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Test History - 테이블 형식 */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>내 테스트 목록</CardTitle>
                  <Badge variant="outline">{tests.length}회 검사</Badge>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-gray-50">
                        <th className="px-4 py-3 text-left font-medium text-gray-600">날짜</th>
                        <th className="px-4 py-3 text-left font-medium text-gray-600">프로토콜</th>
                        <th className="px-4 py-3 text-right font-medium text-gray-600">VO2MAX</th>
                        <th className="px-4 py-3 text-right font-medium text-gray-600">HR MAX</th>
                        <th className="px-4 py-3 text-center font-medium text-gray-600">상태</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tests.filter(test => test && (test.test_id || test.id)).map((test) => (
                        <tr
                          key={test.test_id || test.id}
                          className="border-b hover:bg-blue-50 cursor-pointer transition-colors"
                          tabIndex={0}
                          role="button"
                          onClick={() => onNavigate('metabolism', { testId: test.test_id || test.id })}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              onNavigate('metabolism', { testId: test.test_id || test.id });
                            }
                          }}
                        >
                          <td className="px-4 py-3 text-gray-900 font-medium">
                            {new Date(test.test_date).toLocaleDateString('ko-KR', {
                              year: '2-digit',
                              month: '2-digit',
                              day: '2-digit'
                            })}
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant="outline" className="font-normal">
                              {test.protocol_type || 'RAMP'}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-[#3B82F6] font-semibold">
                            {test.summary?.vo2_max_rel?.toFixed(1) || '-'}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-[#EF4444] font-semibold">
                            {test.summary?.hr_max || '-'}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {test.is_valid !== false ? (
                              <span className="inline-flex items-center gap-1 text-green-600">
                                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                                완료
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-gray-400">
                                <span className="w-2 h-2 bg-gray-300 rounded-full"></span>
                                무효
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {tests.length === 0 && (
                  <div className="p-8 text-center text-gray-500">
                    <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>등록된 테스트가 없습니다.</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}