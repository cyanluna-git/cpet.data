import { useState, useEffect } from 'react';
import { MetabolismChart } from './MetabolismChart';
import { MetabolismPatternChart } from './MetabolismPatternChart';
import { sampleSubjects, generateMetabolismData, getFatMaxPoint } from '@/utils/sampleData';
import { Navigation } from '@/components/layout/Navigation';

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

export function MetabolismPage({ user, onLogout, onNavigate }: MetabolismPageProps) {
  const [selectedSubjectId, setSelectedSubjectId] = useState<string | null>(null);
  const [showCohortAverage, setShowCohortAverage] = useState(false);
  
  // For subjects, only show their own data
  const availableSubjects = user.role === 'subject' 
    ? sampleSubjects.filter(s => s.id === user.id)
    : sampleSubjects;
  
  // Initialize with first subject or user's subject
  useEffect(() => {
    if (user.role === 'subject' && user.id) {
      setSelectedSubjectId(user.id);
    } else if (availableSubjects.length > 0) {
      setSelectedSubjectId(availableSubjects[0].id);
    }
  }, [user.role, user.id]);
  
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
          ) : selectedSubject ? (
            <div className="mb-8">
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
          
          {/* Pattern Comparison - Only for researchers/admin */}
          {user.role !== 'subject' && (
            <div>
              <h2 className="text-2xl font-bold text-gray-900 mb-4">대사 패턴 비교</h2>
              <p className="text-gray-600 mb-6">
                서로 다른 훈련 유형에 따른 대사 프로필의 차이를 확인할 수 있습니다.
                파란색은 지방 산화, 빨간색은 탄수화물 산화를 나타냅니다.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <MetabolismPatternChart pattern="Crossfit" />
                <MetabolismPatternChart pattern="Hyrox" />
              </div>
              
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