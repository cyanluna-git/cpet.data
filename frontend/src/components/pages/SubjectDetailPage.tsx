import { useState, useEffect } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Activity, Calendar, TrendingUp } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '@/lib/api';
import { toast } from 'sonner';

interface SubjectDetailPageProps {
  user: any;
  subjectId: string;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

export function SubjectDetailPage({ user, subjectId, onLogout, onNavigate }: SubjectDetailPageProps) {
  const [subject, setSubject] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSubject();
  }, [subjectId]);

  async function loadSubject() {
    try {
      const data = await api.getSubject(subjectId);
      setSubject(data);
    } catch (error) {
      console.error('Failed to load subject:', error);
      toast.error('피험자 정보 로딩 실패');
    } finally {
      setLoading(false);
    }
  }

  if (loading || !subject) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navigation user={user} currentView="subject-detail" onNavigate={onNavigate} onLogout={onLogout} />
        <div className="flex items-center justify-center h-96">
          <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
        </div>
      </div>
    );
  }

  const tests = subject.tests || [];
  
  // Prepare timeline data
  const timelineData = tests.map((test: any) => ({
    date: new Date(test.test_date).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    vo2_max: test.summary?.vo2_max_rel,
    fat_max_hr: test.summary?.fat_max_hr,
    hr_max: test.summary?.hr_max
  })).reverse();

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="subject-detail" onNavigate={onNavigate} onLogout={onLogout} />
      
      <div className="max-w-7xl mx-auto px-6 py-8">
        <Button variant="ghost" onClick={() => onNavigate('subject-list')} className="mb-4 -ml-2">
          <ArrowLeft className="w-4 h-4 mr-2" />
          피험자 목록으로
        </Button>

        {/* Profile Header */}
        <Card className="mb-6">
          <CardContent className="pt-6">
            <div className="flex items-start gap-6">
              <div className="w-24 h-24 bg-gradient-to-br from-[#2563EB] to-[#3B82F6] rounded-full flex items-center justify-center text-white font-bold text-4xl flex-shrink-0">
                {subject.name?.charAt(0) || subject.research_id?.charAt(0)}
              </div>
              
              <div className="flex-1">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h1 className="text-3xl font-bold text-gray-900 mb-2">{subject.research_id}</h1>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">{subject.gender === 'M' ? '남성' : '여성'}</Badge>
                      <Badge variant="outline">{new Date().getFullYear() - subject.birth_year}세</Badge>
                      {subject.training_level && (
                        <Badge variant="secondary">{subject.training_level}</Badge>
                      )}
                    </div>
                  </div>
                  <Button variant="outline" onClick={() => toast.info('편집 기능은 곧 추가됩니다')}>
                    편집
                  </Button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-gray-500 mb-1">키</p>
                    <p className="font-semibold text-gray-900">{subject.height_cm} cm</p>
                  </div>
                  <div>
                    <p className="text-gray-500 mb-1">체중</p>
                    <p className="font-semibold text-gray-900">{subject.weight_kg} kg</p>
                  </div>
                  <div>
                    <p className="text-gray-500 mb-1">BMI</p>
                    <p className="font-semibold text-gray-900">
                      {(subject.weight_kg / Math.pow(subject.height_cm / 100, 2)).toFixed(1)}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-500 mb-1">총 검사 수</p>
                    <p className="font-semibold text-gray-900">{tests.length}회</p>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3 max-w-md">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="history">Test History</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            {tests.length === 0 ? (
              <Card className="p-12 text-center">
                <Activity className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">검사 기록이 없습니다</h3>
                <p className="text-gray-600">이 피험자의 첫 번째 테스트를 업로드하세요.</p>
              </Card>
            ) : (
              <>
                {/* Timeline Chart */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-[#2563EB]" />
                      주요 지표 변화 추이
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={timelineData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip />
                          <Line
                            type="monotone"
                            dataKey="vo2_max"
                            stroke="#3B82F6"
                            strokeWidth={2}
                            name="VO2 MAX (mL/kg/min)"
                          />
                          <Line
                            type="monotone"
                            dataKey="fat_max_hr"
                            stroke="#10B981"
                            strokeWidth={2}
                            name="FATMAX HR (bpm)"
                          />
                          <Line
                            type="monotone"
                            dataKey="hr_max"
                            stroke="#EF4444"
                            strokeWidth={2}
                            name="HR MAX (bpm)"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>

                {/* Latest Test Summary */}
                <Card>
                  <CardHeader>
                    <CardTitle>최근 검사 결과</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                      <div>
                        <p className="text-sm text-gray-500 mb-2">VO2 MAX</p>
                        <p className="text-2xl font-bold text-[#3B82F6]">
                          {tests[0]?.summary?.vo2_max_rel?.toFixed(1)}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">mL/kg/min</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 mb-2">HR MAX</p>
                        <p className="text-2xl font-bold text-[#EF4444]">
                          {tests[0]?.summary?.hr_max}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">bpm</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 mb-2">FATMAX</p>
                        <p className="text-2xl font-bold text-[#10B981]">
                          {tests[0]?.summary?.fat_max_hr}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">bpm</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 mb-2">RER MAX</p>
                        <p className="text-2xl font-bold text-[#A855F7]">
                          {tests[0]?.summary?.rer_max?.toFixed(2)}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">ratio</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>

          <TabsContent value="history" className="space-y-4">
            {tests.length === 0 ? (
              <Card className="p-12 text-center">
                <Calendar className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">검사 기록이 없습니다</h3>
              </Card>
            ) : (
              tests.map((test: any) => (
                <Card
                  key={test.id}
                  className="hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => onNavigate('test-view', { testId: test.id })}
                >
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-[#2563EB] rounded-full flex items-center justify-center">
                          <Activity className="w-6 h-6 text-white" />
                        </div>
                        <div>
                          <p className="font-semibold text-gray-900">
                            {new Date(test.test_date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}
                          </p>
                          <p className="text-sm text-gray-500">{test.protocol_type} · {test.protocol_name}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <p className="text-xs text-gray-500">VO2 MAX</p>
                            <p className="font-bold text-[#3B82F6]">{test.summary?.vo2_max_rel?.toFixed(1)}</p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">HR MAX</p>
                            <p className="font-bold text-[#EF4444]">{test.summary?.hr_max}</p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">FATMAX</p>
                            <p className="font-bold text-[#10B981]">{test.summary?.fat_max_hr}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          <TabsContent value="notes">
            <Card className="p-12 text-center">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">연구 노트</h3>
              <p className="text-gray-600">노트 기능은 곧 추가됩니다.</p>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
