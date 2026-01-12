import { useState, useEffect } from 'react';
import { Navigation } from './Navigation';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Badge } from './ui/badge';
import { Checkbox } from './ui/checkbox';
import { Label } from './ui/label';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea
} from 'recharts';
import { ArrowLeft, Download, ZoomIn, ZoomOut, RotateCcw, Activity, Heart, Wind } from 'lucide-react';
import { api } from '../utils/api';
import { toast } from 'sonner';

interface SingleTestViewProps {
  user: any;
  testId: string;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

const CHART_COLORS = {
  hr: '#EF4444',
  vo2: '#3B82F6',
  vco2: '#10B981',
  rer: '#A855F7',
  fat_oxidation: '#F97316',
  cho_oxidation: '#FBBF24',
  bike_power: '#6B7280'
};

const PHASE_COLORS = {
  Rest: '#E5E7EB',
  Warmup: '#FEF3C7',
  Exercise: 'transparent',
  Peak: '#FFEDD5',
  Recovery: '#E5E7EB'
};

export function SingleTestView({ user, testId, onLogout, onNavigate }: SingleTestViewProps) {
  const [test, setTest] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [xAxis, setXAxis] = useState<'time_sec' | 'bike_power'>('time_sec');
  const [visibleLines, setVisibleLines] = useState({
    hr: true,
    vo2: true,
    vco2: false,
    rer: true,
    fat_oxidation: true,
    cho_oxidation: false
  });

  useEffect(() => {
    loadTest();
  }, [testId]);

  async function loadTest() {
    try {
      const data = await api.getTest(testId);
      setTest(data);
    } catch (error) {
      console.error('Failed to load test:', error);
      toast.error('테스트 데이터 로딩 실패');
    } finally {
      setLoading(false);
    }
  }

  function toggleLine(line: keyof typeof visibleLines) {
    setVisibleLines(prev => ({ ...prev, [line]: !prev[line] }));
  }

  if (loading || !test) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Navigation user={user} currentView="test-view" onNavigate={onNavigate} onLogout={onLogout} />
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-gray-600">테스트 데이터 로딩 중...</p>
          </div>
        </div>
      </div>
    );
  }

  const subject = test.subject || test.metadata;

  // Prepare chart data
  const chartData = test.timeseries?.map((point: any) => ({
    ...point,
    time_display: `${Math.floor(point.time_sec / 60)}:${String(point.time_sec % 60).padStart(2, '0')}`
  })) || [];

  // Get phase segments for background coloring
  const phases = test.phases || {};
  const phaseSegments = [
    { start: 0, end: phases.rest_end_sec, phase: 'Rest' },
    { start: phases.rest_end_sec, end: phases.warmup_end_sec, phase: 'Warmup' },
    { start: phases.warmup_end_sec, end: phases.exercise_end_sec, phase: 'Exercise' },
    { start: phases.exercise_end_sec, end: phases.total_duration_sec, phase: 'Recovery' }
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="test-view" onNavigate={onNavigate} onLogout={onLogout} />
      
      <div className="max-w-[1600px] mx-auto px-6 py-6">
        {/* Header */}
        <div className="mb-6">
          <Button variant="ghost" onClick={() => onNavigate('researcher-dashboard')} className="mb-4 -ml-2">
            <ArrowLeft className="w-4 h-4 mr-2" />
            대시보드로 돌아가기
          </Button>
          
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Single Test Analysis</h1>
              <div className="flex items-center gap-3 text-sm text-gray-600">
                <span className="font-semibold">피험자: {subject?.research_id || subject?.name}</span>
                <span>·</span>
                <span>{new Date(test.test_date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })}</span>
                <span>·</span>
                <Badge variant="outline" className="font-medium">{test.protocol_type || 'BxB'} Protocol</Badge>
              </div>
            </div>
            
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => toast.info('비교 기능은 곧 추가됩니다')}>
                비교 추가
              </Button>
              <Button className="bg-[#2563EB]" onClick={() => toast.info('PDF 다운로드 기능은 곧 추가됩니다')}>
                <Download className="w-4 h-4 mr-2" />
                리포트 다운로드
              </Button>
            </div>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <Card className="border-l-4 border-l-[#3B82F6]">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-gray-600 flex items-center gap-2">
                <Activity className="w-4 h-4" />
                VO2 MAX
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-[#3B82F6]">{test.summary?.vo2_max_rel?.toFixed(1) || 'N/A'}</div>
              <p className="text-xs text-gray-500 mt-1">mL/kg/min · {test.summary?.vo2_max_percent_pred?.toFixed(0)}% Pred</p>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-[#EF4444]">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-gray-600 flex items-center gap-2">
                <Heart className="w-4 h-4" />
                HR MAX
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-[#EF4444]">{test.summary?.hr_max || 'N/A'}</div>
              <p className="text-xs text-gray-500 mt-1">bpm · {test.summary?.hr_max_percent_pred?.toFixed(0)}% Pred</p>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-[#10B981]">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-gray-600 flex items-center gap-2">
                <Wind className="w-4 h-4" />
                FATMAX
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-[#10B981]">{test.summary?.fat_max_hr || 'N/A'}</div>
              <p className="text-xs text-gray-500 mt-1">bpm at {test.summary?.fat_max_watt}W</p>
            </CardContent>
          </Card>

          <Card className="border-l-4 border-l-[#F97316]">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-gray-600">MFO</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-[#F97316]">{test.summary?.mfo?.toFixed(2) || 'N/A'}</div>
              <p className="text-xs text-gray-500 mt-1">g/min</p>
            </CardContent>
          </Card>
        </div>

        {/* Main Chart */}
        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>인터랙티브 차트 분석</CardTitle>
              <div className="flex items-center gap-4">
                {/* X-Axis Toggle */}
                <div className="flex items-center gap-2 border rounded-lg p-1">
                  <Button
                    size="sm"
                    variant={xAxis === 'time_sec' ? 'default' : 'ghost'}
                    onClick={() => setXAxis('time_sec')}
                    className="h-8"
                  >
                    시간
                  </Button>
                  <Button
                    size="sm"
                    variant={xAxis === 'bike_power' ? 'default' : 'ghost'}
                    onClick={() => setXAxis('bike_power')}
                    className="h-8"
                  >
                    부하 (W)
                  </Button>
                </div>

                {/* Zoom Controls */}
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" onClick={() => toast.info('확대 기능')}>
                    <ZoomIn className="w-4 h-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => toast.info('축소 기능')}>
                    <ZoomOut className="w-4 h-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => toast.info('리셋 기능')}>
                    <RotateCcw className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>

            {/* Line Toggles */}
            <div className="grid grid-cols-3 md:grid-cols-6 gap-4 mt-4 pt-4 border-t">
              <div className="flex items-center space-x-2">
                <Checkbox id="hr" checked={visibleLines.hr} onCheckedChange={() => toggleLine('hr')} />
                <Label htmlFor="hr" className="flex items-center gap-2 cursor-pointer">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CHART_COLORS.hr }}></div>
                  <span className="text-sm">HR</span>
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox id="vo2" checked={visibleLines.vo2} onCheckedChange={() => toggleLine('vo2')} />
                <Label htmlFor="vo2" className="flex items-center gap-2 cursor-pointer">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CHART_COLORS.vo2 }}></div>
                  <span className="text-sm">VO2</span>
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox id="vco2" checked={visibleLines.vco2} onCheckedChange={() => toggleLine('vco2')} />
                <Label htmlFor="vco2" className="flex items-center gap-2 cursor-pointer">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CHART_COLORS.vco2 }}></div>
                  <span className="text-sm">VCO2</span>
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox id="rer" checked={visibleLines.rer} onCheckedChange={() => toggleLine('rer')} />
                <Label htmlFor="rer" className="flex items-center gap-2 cursor-pointer">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CHART_COLORS.rer }}></div>
                  <span className="text-sm">RER</span>
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox id="fat" checked={visibleLines.fat_oxidation} onCheckedChange={() => toggleLine('fat_oxidation')} />
                <Label htmlFor="fat" className="flex items-center gap-2 cursor-pointer">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CHART_COLORS.fat_oxidation }}></div>
                  <span className="text-sm">Fat Ox</span>
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox id="cho" checked={visibleLines.cho_oxidation} onCheckedChange={() => toggleLine('cho_oxidation')} />
                <Label htmlFor="cho" className="flex items-center gap-2 cursor-pointer">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CHART_COLORS.cho_oxidation }}></div>
                  <span className="text-sm">CHO Ox</span>
                </Label>
              </div>
            </div>
          </CardHeader>

          <CardContent>
            <div className="h-[500px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  
                  {/* Phase Background Areas */}
                  {xAxis === 'time_sec' && phaseSegments.map((segment, i) => (
                    segment.phase !== 'Exercise' && (
                      <ReferenceArea
                        key={i}
                        x1={segment.start}
                        x2={segment.end}
                        fill={PHASE_COLORS[segment.phase as keyof typeof PHASE_COLORS]}
                        fillOpacity={0.3}
                      />
                    )
                  ))}
                  
                  <XAxis
                    dataKey={xAxis}
                    label={{ value: xAxis === 'time_sec' ? 'Time (seconds)' : 'Power (Watts)', position: 'insideBottom', offset: -10 }}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
                  
                  <Tooltip
                    contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #E5E7EB', borderRadius: '8px', padding: '12px' }}
                    labelFormatter={(value) => xAxis === 'time_sec' ? `Time: ${Math.floor(Number(value) / 60)}:${String(Number(value) % 60).padStart(2, '0')}` : `Power: ${value}W`}
                  />
                  <Legend wrapperStyle={{ paddingTop: '20px' }} />

                  {/* Marker Lines */}
                  {test.markers?.fatmax && xAxis === 'time_sec' && (
                    <ReferenceLine
                      x={test.markers.fatmax.time_sec}
                      stroke={CHART_COLORS.fat_oxidation}
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      label={{ value: 'FATMAX', position: 'top', fill: CHART_COLORS.fat_oxidation, fontWeight: 'bold' }}
                    />
                  )}

                  {test.markers?.vo2max && xAxis === 'time_sec' && (
                    <ReferenceLine
                      x={test.markers.vo2max.time_sec}
                      stroke={CHART_COLORS.hr}
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      label={{ value: 'VO2MAX', position: 'top', fill: CHART_COLORS.hr, fontWeight: 'bold' }}
                    />
                  )}

                  {/* Data Lines */}
                  {visibleLines.hr && (
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="hr"
                      stroke={CHART_COLORS.hr}
                      strokeWidth={2}
                      dot={false}
                      name="HR (bpm)"
                    />
                  )}

                  {visibleLines.vo2 && (
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="vo2"
                      stroke={CHART_COLORS.vo2}
                      strokeWidth={2}
                      dot={false}
                      name="VO2 (mL/min)"
                    />
                  )}

                  {visibleLines.vco2 && (
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="vco2"
                      stroke={CHART_COLORS.vco2}
                      strokeWidth={2}
                      dot={false}
                      name="VCO2 (mL/min)"
                    />
                  )}

                  {visibleLines.rer && (
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="rer"
                      stroke={CHART_COLORS.rer}
                      strokeWidth={2}
                      dot={false}
                      name="RER"
                    />
                  )}

                  {visibleLines.fat_oxidation && (
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="fat_oxidation"
                      stroke={CHART_COLORS.fat_oxidation}
                      strokeWidth={2}
                      dot={false}
                      name="Fat Ox (g/min)"
                    />
                  )}

                  {visibleLines.cho_oxidation && (
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="cho_oxidation"
                      stroke={CHART_COLORS.cho_oxidation}
                      strokeWidth={2}
                      dot={false}
                      name="CHO Ox (g/min)"
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Phase Summary Table */}
        <Card>
          <CardHeader>
            <CardTitle>구간별 요약</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-3 font-semibold">Phase</th>
                    <th className="text-right p-3 font-semibold">Duration</th>
                    <th className="text-right p-3 font-semibold">Avg HR (bpm)</th>
                    <th className="text-right p-3 font-semibold">Avg VO2 (mL/min)</th>
                    <th className="text-right p-3 font-semibold">Avg RER</th>
                    <th className="text-right p-3 font-semibold">Avg Power (W)</th>
                    <th className="text-right p-3 font-semibold">Fat Ox (g/min)</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {['Rest', 'Warmup', 'Exercise', 'Peak', 'Recovery'].map((phase) => {
                    const phaseData = chartData.filter((d: any) => d.phase === phase);
                    if (phaseData.length === 0) return null;

                    const avg = (key: string) => {
                      const sum = phaseData.reduce((acc: number, d: any) => acc + (d[key] || 0), 0);
                      return (sum / phaseData.length).toFixed(1);
                    };

                    return (
                      <tr key={phase} className="hover:bg-gray-50">
                        <td className="p-3 font-medium">
                          <Badge variant="outline">{phase}</Badge>
                        </td>
                        <td className="text-right p-3">{(phaseData.length * 3 / 60).toFixed(1)} min</td>
                        <td className="text-right p-3">{avg('hr')}</td>
                        <td className="text-right p-3">{avg('vo2')}</td>
                        <td className="text-right p-3">{avg('rer')}</td>
                        <td className="text-right p-3">{avg('bike_power')}</td>
                        <td className="text-right p-3">{avg('fat_oxidation')}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
