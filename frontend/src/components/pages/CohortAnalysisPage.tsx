import { useState, useEffect } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { BarChart3, Users, Download } from 'lucide-react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ZAxis } from 'recharts';
import { api } from '@/lib/api';
import { toast } from 'sonner';

interface CohortAnalysisPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string) => void;
}

export function CohortAnalysisPage({ user, onLogout, onNavigate }: CohortAnalysisPageProps) {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    gender: 'all',
    age_min: undefined,
    age_max: undefined
  });

  useEffect(() => {
    loadCohortStats();
  }, [filters]);

  async function loadCohortStats() {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getCohortStats(filters);
      setStats(data || {
        total_subjects: 0,
        total_tests: 0,
        filters_applied: filters,
        metrics: {}
      });
    } catch (error) {
      console.error('Failed to load cohort stats:', error);
      const errorMsg = error instanceof Error ? error.message : '코호트 통계 로딩 실패';
      setError(errorMsg);
      toast.error(errorMsg);
      setStats({
        total_subjects: 0,
        total_tests: 0,
        filters_applied: filters,
        metrics: {}
      });
    } finally {
      setLoading(false);
    }
  }

  function applyFilter(key: string, value: any) {
    // Handle special "all" or "none" values
    if (value === 'all' || value === 'none') {
      setFilters(prev => ({ ...prev, [key]: undefined }));
    } else {
      setFilters(prev => ({ ...prev, [key]: value || undefined }));
    }
  }

  if (loading && !stats) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navigation user={user} currentView="cohort-analysis" onNavigate={onNavigate} onLogout={onLogout} />
        <div className="flex items-center justify-center h-96">
          {error && <div className="text-red-500">{error}</div>}
          {!error && <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>}
        </div>
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navigation user={user} currentView="cohort-analysis" onNavigate={onNavigate} onLogout={onLogout} />
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <p className="text-red-500 mb-4">{error}</p>
            <Button onClick={() => loadCohortStats()}>다시 시도</Button>
          </div>
        </div>
      </div>
    );
  }

  // Prepare scatter plot data
  const scatterData = stats?.tests?.map((test: any) => ({
    vo2_max: test.summary?.vo2_max_rel,
    fat_max_hr: test.summary?.fat_max_hr,
    hr_max: test.summary?.hr_max
  })).filter((d: any) => d.vo2_max && d.fat_max_hr) || [];

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="cohort-analysis" onNavigate={onNavigate} onLogout={onLogout} />
      
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">코호트 분석</h1>
            <p className="text-gray-600">그룹별 대사 프로파일 비교 및 통계 분석</p>
          </div>
          <Button className="bg-[#2563EB] gap-2" onClick={() => toast.info('엑셀 다운로드 기능은 곧 추가됩니다')}>
            <Download className="w-4 h-4" />
            데이터 내보내기
          </Button>
        </div>

        {/* Filters */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-[#2563EB]" />
              코호트 필터
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="space-y-2">
                <Label>성별</Label>
                <Select value={filters.gender} onValueChange={(value) => applyFilter('gender', value)}>
                  <SelectTrigger>
                    <SelectValue placeholder="전체" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">전체</SelectItem>
                    <SelectItem value="M">남성</SelectItem>
                    <SelectItem value="F">여성</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>최소 연령</Label>
                <Select value={filters.age_min?.toString() || 'none'} onValueChange={(value) => applyFilter('age_min', value === 'none' ? null : parseInt(value))}>
                  <SelectTrigger>
                    <SelectValue placeholder="선택 안함" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">선택 안함</SelectItem>
                    <SelectItem value="20">20세</SelectItem>
                    <SelectItem value="30">30세</SelectItem>
                    <SelectItem value="40">40세</SelectItem>
                    <SelectItem value="50">50세</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>최대 연령</Label>
                <Select value={filters.age_max?.toString() || 'none'} onValueChange={(value) => applyFilter('age_max', value === 'none' ? null : parseInt(value))}>
                  <SelectTrigger>
                    <SelectValue placeholder="선택 안함" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">선택 안함</SelectItem>
                    <SelectItem value="39">39세</SelectItem>
                    <SelectItem value="49">49세</SelectItem>
                    <SelectItem value="59">59세</SelectItem>
                    <SelectItem value="69">69세</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-end">
                <Button
                  className="w-full bg-[#2563EB]"
                  onClick={loadCohortStats}
                  disabled={loading}
                >
                  {loading ? '분석 중...' : '필터 적용'}
                </Button>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-gray-500" />
              <span className="text-sm text-gray-600">
                매칭된 피험자: <span className="font-semibold text-gray-900">{stats?.sample_size || 0}명</span>
                {' · '}
                테스트 수: <span className="font-semibold text-gray-900">{stats?.test_count || 0}회</span>
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Statistics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">VO2 MAX 분포</CardTitle>
            </CardHeader>
            <CardContent>
              {stats?.vo2_max_stats ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-gray-600 mb-1">평균</p>
                      <p className="text-2xl font-bold text-[#3B82F6]">
                        {stats.vo2_max_stats.mean.toFixed(1)}
                      </p>
                      <p className="text-xs text-gray-500">mL/kg/min</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1">중앙값</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {stats.vo2_max_stats.median.toFixed(1)}
                      </p>
                      <p className="text-xs text-gray-500">mL/kg/min</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1">범위</p>
                      <p className="text-xl font-bold text-gray-900">
                        {stats.vo2_max_stats.min.toFixed(1)} - {stats.vo2_max_stats.max.toFixed(1)}
                      </p>
                      <p className="text-xs text-gray-500">mL/kg/min</p>
                    </div>
                  </div>

                  <div className="pt-4 border-t">
                    <p className="text-sm text-gray-600 mb-3">백분위 분포</p>
                    <div className="space-y-2">
                      {['10th', '25th', '75th', '90th'].map((percentile, idx) => {
                        const values = [stats.vo2_max_stats.p10, stats.vo2_max_stats.p25, stats.vo2_max_stats.p75, stats.vo2_max_stats.p90];
                        return (
                          <div key={percentile} className="flex items-center justify-between text-sm">
                            <span className="text-gray-600">{percentile} percentile</span>
                            <Badge variant="outline">{values[idx].toFixed(1)} mL/kg/min</Badge>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-gray-500 text-center py-8">데이터 없음</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">FATMAX HR 분포</CardTitle>
            </CardHeader>
            <CardContent>
              {stats?.fat_max_hr_stats ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-gray-600 mb-1">평균</p>
                      <p className="text-2xl font-bold text-[#10B981]">
                        {stats.fat_max_hr_stats.mean.toFixed(0)}
                      </p>
                      <p className="text-xs text-gray-500">bpm</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1">중앙값</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {stats.fat_max_hr_stats.median.toFixed(0)}
                      </p>
                      <p className="text-xs text-gray-500">bpm</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1">범위</p>
                      <p className="text-xl font-bold text-gray-900">
                        {stats.fat_max_hr_stats.min} - {stats.fat_max_hr_stats.max}
                      </p>
                      <p className="text-xs text-gray-500">bpm</p>
                    </div>
                  </div>

                  <div className="pt-4 border-t">
                    <p className="text-sm text-gray-600 mb-3">백분위 분포</p>
                    <div className="space-y-2">
                      {['10th', '25th', '75th', '90th'].map((percentile, idx) => {
                        const values = [stats.fat_max_hr_stats.p10, stats.fat_max_hr_stats.p25, stats.fat_max_hr_stats.p75, stats.fat_max_hr_stats.p90];
                        return (
                          <div key={percentile} className="flex items-center justify-between text-sm">
                            <span className="text-gray-600">{percentile} percentile</span>
                            <Badge variant="outline">{Math.round(values[idx])} bpm</Badge>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-gray-500 text-center py-8">데이터 없음</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Scatter Plot */}
        <Card>
          <CardHeader>
            <CardTitle>VO2 MAX vs FATMAX HR 상관관계</CardTitle>
          </CardHeader>
          <CardContent>
            {scatterData.length > 0 ? (
              <div className="h-96">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                    <XAxis
                      type="number"
                      dataKey="vo2_max"
                      name="VO2 MAX"
                      unit=" mL/kg/min"
                      label={{ value: 'VO2 MAX (mL/kg/min)', position: 'insideBottom', offset: -10 }}
                    />
                    <YAxis
                      type="number"
                      dataKey="fat_max_hr"
                      name="FATMAX HR"
                      unit=" bpm"
                      label={{ value: 'FATMAX HR (bpm)', angle: -90, position: 'insideLeft' }}
                    />
                    <ZAxis type="number" dataKey="hr_max" range={[50, 400]} />
                    <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                    <Scatter name="Tests" data={scatterData} fill="#2563EB" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-center py-12">
                <BarChart3 className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">선택된 필터에 해당하는 데이터가 없습니다</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}