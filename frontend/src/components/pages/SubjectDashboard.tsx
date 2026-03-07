import { useState, useEffect, useMemo } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Activity, TrendingUp, Heart, Flame, Calendar, Target, Edit2, Check, X } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { extractItems, getErrorMessage } from '@/utils/apiHelpers';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Input } from '@/components/ui/input';

interface SubjectDashboardProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

// 목표 데이터 타입
interface Goal {
  vo2MaxTarget: number | null;
  fatMaxHrTarget: number | null;
  monthlyTestGoal: number;
}

// 로컬 스토리지 키
const GOALS_STORAGE_KEY = 'cpet_user_goals';

export function SubjectDashboard({ user, onLogout, onNavigate }: SubjectDashboardProps) {
  const [subject, setSubject] = useState<any>(null);
  const [tests, setTests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // 목표 설정 상태
  const [goals, setGoals] = useState<Goal>(() => {
    const saved = localStorage.getItem(GOALS_STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return { vo2MaxTarget: null, fatMaxHrTarget: null, monthlyTestGoal: 1 };
      }
    }
    return { vo2MaxTarget: null, fatMaxHrTarget: null, monthlyTestGoal: 1 };
  });
  const [editingGoals, setEditingGoals] = useState(false);
  const [tempGoals, setTempGoals] = useState<Goal>(goals);

  useEffect(() => {
    loadData();
  }, []);

  // 목표 저장
  const saveGoals = () => {
    localStorage.setItem(GOALS_STORAGE_KEY, JSON.stringify(tempGoals));
    setGoals(tempGoals);
    setEditingGoals(false);
    toast.success('목표가 저장되었습니다');
  };

  // 목표 취소
  const cancelGoalEdit = () => {
    setTempGoals(goals);
    setEditingGoals(false);
  };

  async function loadData() {
    try {
      // 일반 유저는 본인 테스트만 조회됨 (백엔드에서 subject role 자동 필터링)
      const testsResponse = await api.getTests();
      const testsData = extractItems<any>(testsResponse);
      setTests(testsData);

      const subjectId = user.subject_id || testsData[0]?.subject_id;
      if (subjectId) {
        const subjectData = await api.getSubject(subjectId);
        setSubject(subjectData);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  // 트렌드 데이터 계산
  const trendData = useMemo(() => {
    if (tests.length < 2) return null;

    return tests
      .slice()
      .sort((a, b) => new Date(a.test_date).getTime() - new Date(b.test_date).getTime())
      .map((test) => ({
        date: new Date(test.test_date).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
        vo2Max: test.vo2_max_rel || null,
        fatMaxHr: test.fat_max_hr || null,
      }))
      .filter(d => d.vo2Max !== null || d.fatMaxHr !== null);
  }, [tests]);

  const inscydReports = subject?.inscyd_reports || [];
  const latestInscyd = inscydReports[0];
  const inscydTrendData = useMemo(() => {
    if (inscydReports.length < 2) return null;

    return inscydReports
      .slice()
      .sort(
        (a: any, b: any) =>
          new Date(a.report_date || a.created_at).getTime() -
          new Date(b.report_date || b.created_at).getTime(),
      )
      .map((report: any) => ({
        date: new Date(report.report_date || report.created_at).toLocaleDateString('ko-KR', {
          month: 'short',
          day: 'numeric',
        }),
        vo2max: report.vo2max_rel_ml_kg_min || null,
        fatmax: report.fatmax_watt || null,
        at: report.at_abs_watt || null,
      }))
      .filter((item: any) => item.vo2max !== null || item.fatmax !== null || item.at !== null);
  }, [inscydReports]);

  // 목표 진행률 계산
  const goalProgress = useMemo(() => {
    const latestTest = tests[0];
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const thisMonthTests = tests.filter(t => new Date(t.test_date) >= monthStart).length;

    return {
      vo2Max: latestTest?.vo2_max_rel && goals.vo2MaxTarget
        ? Math.min(100, Math.round((latestTest.vo2_max_rel / goals.vo2MaxTarget) * 100))
        : null,
      fatMaxHr: latestTest?.fat_max_hr && goals.fatMaxHrTarget
        ? Math.min(100, Math.round((latestTest.fat_max_hr / goals.fatMaxHrTarget) * 100))
        : null,
      monthlyTests: Math.min(100, Math.round((thisMonthTests / goals.monthlyTestGoal) * 100)),
      thisMonthTests,
    };
  }, [tests, goals]);

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
      
      <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
        {/* Welcome */}
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">
            내 대사 프로파일
          </h1>
          <p className="text-gray-600">
            최근 운동 능력 검사 결과와 코호트 비교 분석을 확인하세요.
          </p>
        </div>

        {!latestTest && inscydReports.length === 0 ? (
          <Card className="p-12 text-center">
            <Activity className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">아직 테스트 기록이 없습니다</h3>
            <p className="text-gray-600">CPET 또는 INSCYD 리포트가 업로드되면 결과가 여기에 표시됩니다.</p>
          </Card>
        ) : (
          <>
            {/* Latest Test Results - Hero Section */}
            {latestTest && (
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
                          {latestTest.vo2_max_rel?.toFixed(1) || '-'}
                        </p>
                        <p className="text-xs text-gray-500">mL/kg/min</p>
                      </div>
                    </div>
                    {vo2maxPercentile && latestTest.vo2_max_rel && (
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
                          {latestTest.hr_max || '-'}
                        </p>
                        <p className="text-xs text-gray-500">bpm</p>
                      </div>
                    </div>
                    {latestTest.hr_max && (
                      <div className="mt-4 pt-4 border-t">
                        <p className="text-sm text-gray-600">예측치 대비</p>
                        <p className="text-lg font-semibold text-gray-900">
                          {latestTest.hr_max_percent_pred?.toFixed(0) || '-'}%
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="bg-white rounded-lg p-6 shadow-sm">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-12 h-12 bg-[#10B981] bg-opacity-10 rounded-full flex items-center justify-center">
                        <Flame className="w-6 h-6 text-[#10B981]" />
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">FATMAX 심박수</p>
                        <p className="text-2xl font-bold text-[#10B981]">
                          {latestTest.fat_max_hr || '-'}
                        </p>
                        <p className="text-xs text-gray-500">bpm</p>
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <p className="text-sm text-gray-600">지방 연소 최대 심박수</p>
                      <p className="text-xs text-gray-500 mt-1">
                        운동 강도: {latestTest.fat_max_watt || '-'}W
                      </p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
            )}

            {/* Trend Chart - 테스트가 2개 이상일 때만 */}
            {trendData && trendData.length >= 2 && (
              <Card className="mb-8">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-[#2563EB]" />
                    나의 변화 추이
                  </CardTitle>
                  <CardDescription>
                    지난 테스트들의 결과 변화를 확인하세요
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="h-48 md:h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 12 }}
                          tickLine={false}
                          axisLine={{ stroke: '#e5e7eb' }}
                        />
                        <YAxis
                          yAxisId="left"
                          tick={{ fontSize: 12 }}
                          tickLine={false}
                          axisLine={false}
                          domain={['dataMin - 5', 'dataMax + 5']}
                        />
                        <YAxis
                          yAxisId="right"
                          orientation="right"
                          tick={{ fontSize: 12 }}
                          tickLine={false}
                          axisLine={false}
                          domain={['dataMin - 10', 'dataMax + 10']}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'white',
                            border: '1px solid #e5e7eb',
                            borderRadius: '8px',
                            fontSize: '12px',
                          }}
                          formatter={(value: number, name: string) => [
                            value?.toFixed(1),
                            name === 'vo2Max' ? 'VO2 MAX (ml/kg/min)' : 'FATMAX HR (bpm)'
                          ]}
                        />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="vo2Max"
                          stroke="#3B82F6"
                          strokeWidth={2}
                          dot={{ fill: '#3B82F6', strokeWidth: 2 }}
                          name="vo2Max"
                          connectNulls
                        />
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey="fatMaxHr"
                          stroke="#10B981"
                          strokeWidth={2}
                          dot={{ fill: '#10B981', strokeWidth: 2 }}
                          name="fatMaxHr"
                          connectNulls
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex justify-center gap-6 mt-4 text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-[#3B82F6]"></div>
                      <span className="text-gray-600">VO2 MAX</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-[#10B981]"></div>
                      <span className="text-gray-600">FATMAX HR</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {latestInscyd && (
              <Card className="mb-8 border-t-4 border-t-[#0F766E] bg-gradient-to-br from-emerald-50 to-white">
                <CardHeader>
                  <CardTitle className="text-xl">최신 INSCYD 리포트</CardTitle>
                  <CardDescription className="flex items-center gap-2">
                    <Calendar className="w-4 h-4" />
                    {new Date(latestInscyd.report_date || latestInscyd.created_at).toLocaleDateString('ko-KR', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="bg-white rounded-lg p-6 shadow-sm">
                      <p className="text-sm text-gray-600">VO2max</p>
                      <p className="mt-2 text-2xl font-bold text-[#0F766E]">
                        {latestInscyd.vo2max_rel_ml_kg_min?.toFixed(1) || '-'}
                      </p>
                      <p className="text-xs text-gray-500">mL/kg/min</p>
                    </div>
                    <div className="bg-white rounded-lg p-6 shadow-sm">
                      <p className="text-sm text-gray-600">VLamax</p>
                      <p className="mt-2 text-2xl font-bold text-[#7C3AED]">
                        {latestInscyd.vlamax_mmol_l_s?.toFixed(2) || '-'}
                      </p>
                      <p className="text-xs text-gray-500">mmol/L/s</p>
                    </div>
                    <div className="bg-white rounded-lg p-6 shadow-sm">
                      <p className="text-sm text-gray-600">FatMax</p>
                      <p className="mt-2 text-2xl font-bold text-[#F59E0B]">
                        {latestInscyd.fatmax_watt || '-'}
                      </p>
                      <p className="text-xs text-gray-500">W</p>
                    </div>
                    <div className="bg-white rounded-lg p-6 shadow-sm">
                      <p className="text-sm text-gray-600">AT</p>
                      <p className="mt-2 text-2xl font-bold text-[#DC2626]">
                        {latestInscyd.at_abs_watt || '-'}
                      </p>
                      <p className="text-xs text-gray-500">W</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {inscydTrendData && inscydTrendData.length >= 2 && (
              <Card className="mb-8">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-[#0F766E]" />
                    INSCYD 변화 추이
                  </CardTitle>
                  <CardDescription>
                    정기적으로 받은 INSCYD 리포트의 주요 지표 변화를 확인하세요
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="h-48 md:h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={inscydTrendData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 12 }}
                          tickLine={false}
                          axisLine={{ stroke: '#e5e7eb' }}
                        />
                        <YAxis
                          yAxisId="fitness"
                          tick={{ fontSize: 12 }}
                          tickLine={false}
                          axisLine={false}
                        />
                        <YAxis
                          yAxisId="power"
                          orientation="right"
                          tick={{ fontSize: 12 }}
                          tickLine={false}
                          axisLine={false}
                        />
                        <Tooltip />
                        <Line
                          yAxisId="fitness"
                          type="monotone"
                          dataKey="vo2max"
                          stroke="#0F766E"
                          strokeWidth={2}
                          dot={{ fill: '#0F766E', strokeWidth: 2 }}
                          connectNulls
                        />
                        <Line
                          yAxisId="power"
                          type="monotone"
                          dataKey="fatmax"
                          stroke="#F59E0B"
                          strokeWidth={2}
                          dot={{ fill: '#F59E0B', strokeWidth: 2 }}
                          connectNulls
                        />
                        <Line
                          yAxisId="power"
                          type="monotone"
                          dataKey="at"
                          stroke="#DC2626"
                          strokeWidth={2}
                          dot={{ fill: '#DC2626', strokeWidth: 2 }}
                          connectNulls
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Goals Card */}
            <Card className="mb-8 border-l-4 border-l-[#10B981]">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Target className="w-5 h-5 text-[#10B981]" />
                    나의 목표
                  </CardTitle>
                  {!editingGoals ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setTempGoals(goals);
                        setEditingGoals(true);
                      }}
                    >
                      <Edit2 className="w-4 h-4 mr-1" />
                      편집
                    </Button>
                  ) : (
                    <div className="flex gap-2">
                      <Button variant="ghost" size="sm" onClick={cancelGoalEdit}>
                        <X className="w-4 h-4" />
                      </Button>
                      <Button variant="default" size="sm" onClick={saveGoals}>
                        <Check className="w-4 h-4 mr-1" />
                        저장
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {editingGoals ? (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        VO2 MAX 목표 (ml/kg/min)
                      </label>
                      <Input
                        type="number"
                        placeholder="예: 50"
                        value={tempGoals.vo2MaxTarget || ''}
                        onChange={(e) => setTempGoals({
                          ...tempGoals,
                          vo2MaxTarget: e.target.value ? Number(e.target.value) : null
                        })}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        FATMAX 심박수 목표 (bpm)
                      </label>
                      <Input
                        type="number"
                        placeholder="예: 140"
                        value={tempGoals.fatMaxHrTarget || ''}
                        onChange={(e) => setTempGoals({
                          ...tempGoals,
                          fatMaxHrTarget: e.target.value ? Number(e.target.value) : null
                        })}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        월간 테스트 목표 (회)
                      </label>
                      <Input
                        type="number"
                        min={1}
                        placeholder="예: 2"
                        value={tempGoals.monthlyTestGoal}
                        onChange={(e) => setTempGoals({
                          ...tempGoals,
                          monthlyTestGoal: Math.max(1, Number(e.target.value) || 1)
                        })}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* VO2 MAX 목표 */}
                    {goals.vo2MaxTarget ? (
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-600">VO2 MAX</span>
                          <span className="font-medium">
                            {latestTest?.vo2_max_rel?.toFixed(1) || '-'} / {goals.vo2MaxTarget} ml/kg/min
                          </span>
                        </div>
                        <Progress value={goalProgress.vo2Max || 0} className="h-2" />
                        {goalProgress.vo2Max !== null && goalProgress.vo2Max >= 100 && (
                          <p className="text-xs text-green-600 mt-1">🎉 목표 달성!</p>
                        )}
                      </div>
                    ) : (
                      <div className="text-sm text-gray-500">
                        VO2 MAX 목표를 설정해보세요
                      </div>
                    )}

                    {/* FATMAX HR 목표 */}
                    {goals.fatMaxHrTarget ? (
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-600">FATMAX 심박수</span>
                          <span className="font-medium">
                            {latestTest?.fat_max_hr || '-'} / {goals.fatMaxHrTarget} bpm
                          </span>
                        </div>
                        <Progress value={goalProgress.fatMaxHr || 0} className="h-2" />
                        {goalProgress.fatMaxHr !== null && goalProgress.fatMaxHr >= 100 && (
                          <p className="text-xs text-green-600 mt-1">🎉 목표 달성!</p>
                        )}
                      </div>
                    ) : null}

                    {/* 월간 테스트 목표 */}
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-gray-600">이번 달 테스트</span>
                        <span className="font-medium">
                          {goalProgress.thisMonthTests} / {goals.monthlyTestGoal} 회
                        </span>
                      </div>
                      <Progress value={goalProgress.monthlyTests} className="h-2" />
                      {goalProgress.monthlyTests >= 100 && (
                        <p className="text-xs text-green-600 mt-1">🎉 이번 달 목표 달성!</p>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* What This Means - 데이터가 있을 때만 표시 */}
            {(latestTest?.vo2_max_rel || latestTest?.fat_max_hr || latestTest?.hr_max) && (
              <Card className="mb-8">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-[#2563EB]" />
                    이 결과가 의미하는 것
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {latestTest.vo2_max_rel && (
                    <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
                      <h4 className="font-semibold text-gray-900 mb-2">💪 당신의 유산소 능력</h4>
                      <p className="text-sm text-gray-700">
                        VO2 MAX <span className="font-semibold text-[#2563EB]">{latestTest.vo2_max_rel.toFixed(1)}</span> mL/kg/min는
                        {' '}동일 연령대 평균보다
                        <span className="font-semibold text-[#2563EB]"> {latestTest.vo2_max_rel >= 45 ? '우수한' : latestTest.vo2_max_rel >= 35 ? '양호한' : '보통'} 수준</span>입니다.
                      </p>
                    </div>
                  )}

                  {latestTest.fat_max_hr && (
                    <div className="p-4 bg-green-50 rounded-lg border border-green-100">
                      <h4 className="font-semibold text-gray-900 mb-2">🔥 지방 연소 최적 구간</h4>
                      <p className="text-sm text-gray-700">
                        당신의 지방 연소는 심박수 <span className="font-semibold text-[#10B981]">{latestTest.fat_max_hr} bpm</span>에서
                        가장 효율적입니다. 체중 감량 운동 시 이 심박수를 유지하면 최대 효과를 얻을 수 있습니다.
                      </p>
                    </div>
                  )}

                  {(latestTest.fat_max_hr || latestTest.hr_max) && (
                    <div className="p-4 bg-orange-50 rounded-lg border border-orange-100">
                      <h4 className="font-semibold text-gray-900 mb-2">🎯 추천 운동 강도</h4>
                      <p className="text-sm text-gray-700">
                        {latestTest.fat_max_hr && (
                          <>유산소 운동: 심박수 {Math.floor(latestTest.fat_max_hr * 0.85)}-{latestTest.fat_max_hr} bpm (가벼운 달리기, 사이클링)<br /></>
                        )}
                        {latestTest.hr_max && (
                          <>고강도 훈련: 심박수 {Math.floor(latestTest.hr_max * 0.85)}-{latestTest.hr_max} bpm (인터벌 트레이닝)</>
                        )}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

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
                            {test.vo2_max_rel?.toFixed(1) || '-'}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-[#EF4444] font-semibold">
                            {test.hr_max || '-'}
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
