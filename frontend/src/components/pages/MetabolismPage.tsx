import { useState, useEffect, lazy, Suspense } from 'react';
import { sampleSubjects, generateMetabolismData, getFatMaxPoint } from '@/utils/sampleData';
import { Navigation } from '@/components/layout/Navigation';
import { api, TestAnalysis, Subject as ApiSubject } from '@/lib/api';

// Lazy load chart components to reduce initial bundle size
const MetabolismChart = lazy(() => import('./MetabolismChart').then(module => ({ default: module.MetabolismChart })));
const MetabolismPatternChart = lazy(() => import('./MetabolismPatternChart').then(module => ({ default: module.MetabolismPatternChart })));

interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'researcher' | 'subject';
}

interface MetabolismPageProps {
  user: User;
  onLogout: () => void;
  onNavigate: (view: string) => void;
}

// Transform API analysis data to chart format
function transformAnalysisToChartData(analysis: TestAnalysis) {
  // Group by power for the Power vs Calories chart
  const powerMap = new Map<number, { fat: number[]; cho: number[]; total: number[] }>();

  analysis.timeseries.forEach((point) => {
    const power = Math.round((point.power || 0) / 10) * 10; // Round to nearest 10W
    if (!powerMap.has(power)) {
      powerMap.set(power, { fat: [], cho: [], total: [] });
    }
    const bucket = powerMap.get(power)!;
    if (point.fat_kcal_day) bucket.fat.push(point.fat_kcal_day);
    if (point.cho_kcal_day) bucket.cho.push(point.cho_kcal_day);
    if (point.fat_kcal_day && point.cho_kcal_day) {
      bucket.total.push(point.fat_kcal_day + point.cho_kcal_day);
    }
  });

  // Calculate averages per power level
  const chartData = Array.from(powerMap.entries())
    .map(([power, data]) => ({
      power,
      fatOxidation: data.fat.length > 0 ? Math.round(data.fat.reduce((a, b) => a + b, 0) / data.fat.length) : 0,
      choOxidation: data.cho.length > 0 ? Math.round(data.cho.reduce((a, b) => a + b, 0) / data.cho.length) : 0,
      totalCalories: data.total.length > 0 ? Math.round(data.total.reduce((a, b) => a + b, 0) / data.total.length) : 0,
    }))
    .filter(d => d.power >= 50 && d.power <= 300)
    .sort((a, b) => a.power - b.power);

  return chartData;
}

export function MetabolismPage({ user, onLogout, onNavigate }: MetabolismPageProps) {
  const [selectedSubjectId, setSelectedSubjectId] = useState<string | null>(null);
  const [selectedTestId, setSelectedTestId] = useState<string | null>(null);
  const [showCohortAverage, setShowCohortAverage] = useState(false);
  const [subjects, setSubjects] = useState<ApiSubject[]>([]);
  const [analysis, setAnalysis] = useState<TestAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // For subjects, only show their own data
  const availableSubjects = user.role === 'subject' 
    ? sampleSubjects.filter(s => s.id === user.id)
    : sampleSubjects;
  
  // Load subjects from API
  useEffect(() => {
    async function loadSubjects() {
      try {
        const response = await api.getSubjects({ page_size: 100 });
        setSubjects(response.items);
      } catch (err) {
        console.warn('Failed to load subjects from API, using sample data');
      }
    }
    loadSubjects();
  }, []);

  // Initialize with first subject or user's subject
  useEffect(() => {
    if (user.role === 'subject' && user.id) {
      setSelectedSubjectId(user.id);
    } else if (availableSubjects.length > 0) {
      setSelectedSubjectId(availableSubjects[0].id);
    }
  }, [user.role, user.id]);

  // Load test analysis when subject changes
  useEffect(() => {
    async function loadAnalysis() {
      if (!selectedSubjectId) return;

      setLoading(true);
      setError(null);

      try {
        // Get the subject's latest test
        const testsResponse = await api.getSubjectTests(selectedSubjectId, { page_size: 1 });
        if (testsResponse.items.length > 0) {
          const testId = testsResponse.items[0].id;
          setSelectedTestId(testId);

          // Get analysis data
          const analysisData = await api.getTestAnalysis(testId, '5s');
          setAnalysis(analysisData);
        } else {
          setAnalysis(null);
          setError('이 피험자의 테스트 데이터가 없습니다.');
        }
      } catch (err: any) {
        console.warn('Failed to load analysis from API:', err);
        setError('분석 데이터를 불러올 수 없습니다. 샘플 데이터를 표시합니다.');
        setAnalysis(null);
      } finally {
        setLoading(false);
      }
    }

    if (!showCohortAverage) {
      loadAnalysis();
    }
  }, [selectedSubjectId, showCohortAverage]);
  
  // Calculate cohort average data
  const calculateCohortAverage = () => {
    const allData = sampleSubjects.map(subject => generateMetabolismData(subject));
    const averaged: any[] = [];
    
    // Average across all power points
    for (let i = 0; i < allData[0].length; i++) {
      const powerPoint = {
        power: allData[0][i].power,
        fatOxidation: 0,
        choOxidation: 0,
        totalCalories: 0,
      };
      
      allData.forEach(data => {
        powerPoint.fatOxidation += data[i].fatOxidation;
        powerPoint.choOxidation += data[i].choOxidation;
        powerPoint.totalCalories += data[i].totalCalories;
      });
      
      powerPoint.fatOxidation = Math.round(powerPoint.fatOxidation / allData.length);
      powerPoint.choOxidation = Math.round(powerPoint.choOxidation / allData.length);
      powerPoint.totalCalories = Math.round(powerPoint.totalCalories / allData.length);
      
      averaged.push(powerPoint);
    }
    
    // Find FatMax in averaged data
    let maxFat = 0;
    let fatMaxPower = 80;
    averaged.forEach(point => {
      if (point.fatOxidation > maxFat) {
        maxFat = point.fatOxidation;
        fatMaxPower = point.power;
      }
    });
    
    return { data: averaged, fatMaxPower };
  };
  
  const selectedSubject = availableSubjects.find(s => s.id === selectedSubjectId);
  
  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation
        user={user}
        currentView="metabolism"
        onNavigate={onNavigate}
        onLogout={onLogout}
      />
      
      <div className="p-6">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">메타볼리즘 분석</h1>
            <p className="text-gray-600">
              {user.role === 'subject' 
                ? '귀하의 대사 프로필과 지방 연소 특성을 확인하세요.'
                : '피험자들의 대사 프로필과 코호트 평균을 분석하세요.'}
            </p>
          </div>
          
          {/* Controls - Only for researchers/admin */}
          {user.role !== 'subject' && (
            <div className="mb-6 bg-white rounded-lg shadow-sm border border-gray-200 p-4">
              <div className="flex flex-wrap gap-4 items-center">
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-gray-700">피험자 선택:</label>
                  <select
                    value={selectedSubjectId || ''}
                    onChange={(e) => {
                      setSelectedSubjectId(e.target.value);
                      setShowCohortAverage(false);
                    }}
                    className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={showCohortAverage}
                  >
                    {availableSubjects.map(subject => (
                      <option key={subject.id} value={subject.id}>
                        {subject.name} ({subject.research_id})
                      </option>
                    ))}
                  </select>
                </div>
                
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="cohortAverage"
                    checked={showCohortAverage}
                    onChange={(e) => setShowCohortAverage(e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                  />
                  <label htmlFor="cohortAverage" className="text-sm font-medium text-gray-700">
                    코호트 평균 표시
                  </label>
                </div>
              </div>
            </div>
          )}
          
          {/* Main Chart */}
          <Suspense fallback={
            <div className="mb-8 bg-white rounded-lg shadow-sm border border-gray-200 p-8">
              <div className="animate-pulse">
                <div className="h-8 bg-gray-200 rounded w-1/4 mb-4"></div>
                <div className="h-96 bg-gray-100 rounded"></div>
              </div>
            </div>
          }>
            {showCohortAverage ? (
              <div className="mb-8">
                {(() => {
                  const cohortData = calculateCohortAverage();
                  return (
                    <MetabolismChart
                      data={cohortData.data}
                      fatMaxPower={cohortData.fatMaxPower}
                      duration="평균"
                      tss={95}
                      title="코호트 평균 메타볼리즘"
                      subjectName={`전체 피험자 (n=${sampleSubjects.length})`}
                    />
                  );
                })()}
              </div>
            ) : loading ? (
              <div className="mb-8 bg-white rounded-lg shadow-sm border border-gray-200 p-8">
                <div className="animate-pulse">
                  <div className="h-8 bg-gray-200 rounded w-1/4 mb-4"></div>
                  <div className="h-96 bg-gray-100 rounded"></div>
                </div>
                <p className="text-center text-gray-500 mt-4">분석 데이터 로딩 중...</p>
              </div>
            ) : analysis ? (
              <div className="mb-8">
                {(() => {
                  // Use real API data
                  const chartData = transformAnalysisToChartData(analysis);
                  const fatMaxPower = analysis.fatmax?.fat_max_watt || 130;
                  const duration = analysis.exercise_duration_sec
                    ? `${Math.floor(analysis.exercise_duration_sec / 60)}:${String(Math.floor(analysis.exercise_duration_sec % 60)).padStart(2, '0')}`
                    : '0:00';
                  
                  // Find subject name
                  const subject = availableSubjects.find(s => s.id === selectedSubjectId);
                  const subjectName = subject ? `${subject.name} (${subject.research_id})` : selectedSubjectId;

                  return (
                    <MetabolismChart
                      data={chartData}
                      fatMaxPower={fatMaxPower}
                      duration={duration}
                      tss={89}
                      subjectName={subjectName}
                    />
                  );
                })()}

                {/* Analysis Summary Card */}
                <div className="mt-6 bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">분석 요약</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="text-center p-3 bg-orange-50 rounded-lg">
                      <p className="text-sm text-gray-600">FATMAX</p>
                      <p className="text-xl font-bold text-orange-600">
                        {analysis.fatmax?.fat_max_watt?.toFixed(0) || '-'} W
                      </p>
                      <p className="text-xs text-gray-500">HR: {analysis.fatmax?.fat_max_hr || '-'} bpm</p>
                    </div>
                    <div className="text-center p-3 bg-blue-50 rounded-lg">
                      <p className="text-sm text-gray-600">VO2max</p>
                      <p className="text-xl font-bold text-blue-600">
                        {analysis.vo2max?.vo2_max_rel?.toFixed(1) || '-'} ml/kg/min
                      </p>
                      <p className="text-xs text-gray-500">HR: {analysis.vo2max?.hr_max || '-'} bpm</p>
                    </div>
                    <div className="text-center p-3 bg-green-50 rounded-lg">
                      <p className="text-sm text-gray-600">총 지방 연소</p>
                      <p className="text-xl font-bold text-green-600">
                        {analysis.total_fat_burned_g?.toFixed(1) || '-'} g
                      </p>
                    </div>
                    <div className="text-center p-3 bg-purple-50 rounded-lg">
                      <p className="text-sm text-gray-600">평균 RER</p>
                      <p className="text-xl font-bold text-purple-600">
                        {analysis.avg_rer?.toFixed(2) || '-'}
                      </p>
                    </div>
                  </div>

                  {/* VT Thresholds */}
                  {(analysis.vt1_hr || analysis.vt2_hr) && (
                    <div className="mt-4 pt-4 border-t">
                      <h4 className="text-sm font-medium text-gray-700 mb-2">환기 역치</h4>
                      <div className="flex gap-6 text-sm">
                        {analysis.vt1_hr && (
                          <span className="text-gray-600">
                            VT1: HR {analysis.vt1_hr} bpm / VO2 {analysis.vt1_vo2?.toFixed(0)} ml/min
                          </span>
                        )}
                        {analysis.vt2_hr && (
                          <span className="text-gray-600">
                            VT2: HR {analysis.vt2_hr} bpm / VO2 {analysis.vt2_vo2?.toFixed(0)} ml/min
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : selectedSubject ? (
              <div className="mb-8">
                {/* Fallback to sample data */}
                {error && (
                  <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-800 text-sm">
                    {error}
                  </div>
                )}
                {(() => {
                  const metabolismData = generateMetabolismData(selectedSubject);
                  const fatMaxPoint = getFatMaxPoint(selectedSubject);
                  return (
                    <MetabolismChart
                      data={metabolismData}
                      fatMaxPower={fatMaxPoint.power}
                      duration={fatMaxPoint.duration}
                      tss={fatMaxPoint.tss}
                      subjectName={`${selectedSubject.name} (${selectedSubject.research_id})`}
                    />
                  );
                })()}
              </div>
            ) : null}
          </Suspense>
          
          {/* Pattern Comparison - Only for researchers/admin */}
          {user.role !== 'subject' && (
            <div>
              <h2 className="text-2xl font-bold text-gray-900 mb-4">대사 패턴 비교</h2>
              <p className="text-gray-600 mb-6">
                서로 다른 훈련 유형에 따른 대사 프로필의 차이를 확인할 수 있습니다.
                파란색은 지방 산화, 빨간색은 탄수화물 산화를 나타냅니다.
              </p>
              
              <Suspense fallback={
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 animate-pulse">
                    <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
                    <div className="h-64 bg-gray-100 rounded"></div>
                  </div>
                  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 animate-pulse">
                    <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
                    <div className="h-64 bg-gray-100 rounded"></div>
                  </div>
                </div>
              }>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <MetabolismPatternChart pattern="Crossfit" />
                  <MetabolismPatternChart pattern="Hyrox" />
                </div>
              </Suspense>
              
              <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
                <h3 className="text-lg font-semibold text-blue-900 mb-3">패턴 해석</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
                  <div>
                    <h4 className="font-semibold text-blue-800 mb-2">Crossfit 패턴</h4>
                    <p className="text-gray-700 leading-relaxed">
                      초기에 지방 산화가 빠르게 증가하여 피크에 도달한 후 급격히 감소합니다.
                      고강도 인터벌 트레이닝에 적합한 패턴으로, 빠른 에너지 전환이 특징입니다.
                    </p>
                  </div>
                  <div>
                    <h4 className="font-semibold text-blue-800 mb-2">Hyrox 패턴</h4>
                    <p className="text-gray-700 leading-relaxed">
                      지방 산화가 더 오래 지속되며 완만하게 감소합니다.
                      지구력 운동에 적합한 패턴으로, 장시간 지방을 효율적으로 연소할 수 있습니다.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* Subject's own pattern info */}
          {user.role === 'subject' && selectedSubject && (
            <div className="mt-8">
              <h2 className="text-2xl font-bold text-gray-900 mb-4">귀하의 대사 패턴</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <MetabolismPatternChart pattern={selectedSubject.metabolic_pattern as 'Crossfit' | 'Hyrox'} />
                
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-blue-900 mb-3">
                    {selectedSubject.metabolic_pattern} 패턴
                  </h3>
                  <p className="text-gray-700 leading-relaxed mb-4">
                    {selectedSubject.metabolic_pattern === 'Crossfit' ? (
                      <>
                        귀하는 <strong>Crossfit 타입</strong>의 대사 프로필을 가지고 있습니다.
                        초기에 지방을 효과적으로 연소하며, 고강도 인터벌 트레이닝에 적합합니다.
                      </>
                    ) : (
                      <>
                        귀하는 <strong>Hyrox 타입</strong>의 대사 프로필을 가지고 있습니다.
                        장시간 지방을 효율적으로 연소할 수 있어 지구력 운동에 적합합니다.
                      </>
                    )}
                  </p>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-start gap-2">
                      <div className="w-2 h-2 bg-blue-600 rounded-full mt-1.5"></div>
                      <p className="text-gray-700">
                        <strong>지방 산화:</strong> {selectedSubject.metabolic_pattern === 'Crossfit' 
                          ? '초기 피크 후 빠른 감소' 
                          : '지속적이고 안정적인 연소'}
                      </p>
                    </div>
                    <div className="flex items-start gap-2">
                      <div className="w-2 h-2 bg-red-600 rounded-full mt-1.5"></div>
                      <p className="text-gray-700">
                        <strong>탄수화물 산화:</strong> {selectedSubject.metabolic_pattern === 'Crossfit'
                          ? '빠른 증가율'
                          : '완만한 증가'}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* All subjects overview - Only for researchers/admin */}
          {user.role !== 'subject' && !showCohortAverage && (
            <div className="mt-12">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">전체 피험자 개요</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {sampleSubjects.map(subject => {
                  const fatMaxPoint = getFatMaxPoint(subject);
                  return (
                    <div
                      key={subject.id}
                      className={`bg-white rounded-lg shadow-sm border-2 p-5 cursor-pointer transition-all ${
                        selectedSubjectId === subject.id
                          ? 'border-blue-500 shadow-md'
                          : 'border-gray-200 hover:border-blue-300'
                      }`}
                      onClick={() => setSelectedSubjectId(subject.id)}
                    >
                      <h3 className="text-lg font-semibold text-gray-900 mb-1">
                        {subject.name}
                      </h3>
                      <p className="text-sm text-gray-500 mb-3">{subject.research_id}</p>
                      
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-600">FatMax:</span>
                          <span className="font-semibold text-gray-900">{fatMaxPoint.power} W</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">패턴:</span>
                          <span className="font-semibold text-blue-600">{subject.metabolic_pattern}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Duration:</span>
                          <span className="font-medium text-gray-700">{fatMaxPoint.duration}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">TSS:</span>
                          <span className="font-medium text-gray-700">{fatMaxPoint.tss}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}