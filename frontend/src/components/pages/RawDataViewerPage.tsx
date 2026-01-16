import { useEffect, useState, useRef, useCallback } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Database, Download, ChevronLeft, ChevronRight, Settings2, Check, User, Calendar } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage, getAuthToken } from '@/utils/apiHelpers';

interface RawDataViewerPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

interface TestOption {
  test_id: string;
  source_filename: string;
  test_date: string;
  subject_id: string;
  subject_name?: string;
}

interface SubjectOption {
  id: string;
  name: string;
  research_id: string;
}

interface BreathDataRow {
  id: number;
  time: string;
  t_sec: number | null;
  rf: number | null;
  vt: number | null;
  vo2: number | null;
  vco2: number | null;
  ve: number | null;
  hr: number | null;
  vo2_hr: number | null;
  bike_power: number | null;
  bike_torque: number | null;
  cadence: number | null;
  feo2: number | null;
  feco2: number | null;
  feto2: number | null;
  fetco2: number | null;
  ve_vo2: number | null;
  ve_vco2: number | null;
  rer: number | null;
  fat_oxidation: number | null;
  cho_oxidation: number | null;
  vo2_rel: number | null;
  mets: number | null;
  ee_total: number | null;
  phase: string | null;
  data_source: string | null;
  is_valid: boolean;
}

interface RawDataResponse {
  test_id: string;
  source_filename: string;
  test_date: string;
  subject_name: string | null;
  total_rows: number;
  data: BreathDataRow[];
}

// 컬럼 그룹 정의
interface ColumnDef {
  key: string;
  label: string;
  group: 'fixed' | 'basic' | 'respiratory' | 'metabolic' | 'cardio';
  format: (v: any) => string;
}

// 고정 컬럼 (항상 왼쪽에 표시)
const FIXED_COLUMNS: ColumnDef[] = [
  { key: 't_sec', label: 'Time(s)', group: 'fixed', format: (v: number | null) => v?.toFixed(0) ?? '-' },
  { key: 'phase', label: 'Phase', group: 'fixed', format: (v: string | null) => v ?? '-' },
];

// 선택 가능한 컬럼 (그룹별 정의)
const SELECTABLE_COLUMNS: ColumnDef[] = [
  // 기본 지표
  { key: 'hr', label: 'HR', group: 'basic', format: (v: number | null) => v?.toString() ?? '-' },
  { key: 'bike_power', label: 'Power(W)', group: 'basic', format: (v: number | null) => v?.toString() ?? '-' },
  { key: 'cadence', label: 'Cadence', group: 'basic', format: (v: number | null) => v?.toString() ?? '-' },
  { key: 'mets', label: 'METs', group: 'basic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  
  // 호흡 지표
  { key: 've', label: 'VE', group: 'respiratory', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'vt', label: 'VT', group: 'respiratory', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'rf', label: 'RF', group: 'respiratory', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'feto2', label: 'FetO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'fetco2', label: 'FetCO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'feo2', label: 'FeO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'feco2', label: 'FeCO2', group: 'respiratory', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  
  // 대사 지표
  { key: 'vo2', label: 'VO2', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'vco2', label: 'VCO2', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'rer', label: 'RER', group: 'metabolic', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'fat_oxidation', label: 'Fat(g/min)', group: 'metabolic', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'cho_oxidation', label: 'CHO(g/min)', group: 'metabolic', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'vo2_rel', label: 'VO2/kg', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'ee_total', label: 'EE', group: 'metabolic', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  
  // 심폐 지표
  { key: 'vo2_hr', label: 'VO2/HR', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 've_vo2', label: 'VE/VO2', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 've_vco2', label: 'VE/VCO2', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'bike_torque', label: 'Torque', group: 'cardio', format: (v: number | null) => v?.toFixed(1) ?? '-' },
];

// 그룹 정보
const COLUMN_GROUPS = {
  basic: { label: '기본', color: 'bg-blue-100 text-blue-800' },
  respiratory: { label: '호흡', color: 'bg-green-100 text-green-800' },
  metabolic: { label: '대사', color: 'bg-orange-100 text-orange-800' },
  cardio: { label: '심폐', color: 'bg-purple-100 text-purple-800' },
};

// 기본 선택 컬럼
const DEFAULT_SELECTED_COLUMNS = ['hr', 'vo2', 'vco2', 've', 'rer', 'fat_oxidation', 'cho_oxidation', 'bike_power', 'mets'];

const PAGE_SIZE = 50;

export function RawDataViewerPage({ user, onLogout, onNavigate }: RawDataViewerPageProps) {
  // 피험자 및 테스트 상태
  const [subjects, setSubjects] = useState<SubjectOption[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>('');
  const [tests, setTests] = useState<TestOption[]>([]);
  const [filteredTests, setFilteredTests] = useState<TestOption[]>([]);
  const [selectedTestId, setSelectedTestId] = useState<string>('');
  const [rawData, setRawData] = useState<RawDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingSubjects, setLoadingSubjects] = useState(true);
  const [loadingTests, setLoadingTests] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  
  // 컬럼 선택 상태
  const [selectedColumns, setSelectedColumns] = useState<string[]>(DEFAULT_SELECTED_COLUMNS);
  const [showColumnSelector, setShowColumnSelector] = useState(false);
  const columnSelectorRef = useRef<HTMLDivElement>(null);

  // 외부 클릭 시 컬럼 선택기 닫기
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (columnSelectorRef.current && !columnSelectorRef.current.contains(event.target as Node)) {
        setShowColumnSelector(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 컬럼 토글
  const toggleColumn = useCallback((key: string) => {
    setSelectedColumns(prev => 
      prev.includes(key) 
        ? prev.filter(k => k !== key)
        : [...prev, key]
    );
  }, []);

  // 그룹 전체 선택/해제
  const toggleGroup = useCallback((group: string) => {
    const groupColumns = SELECTABLE_COLUMNS.filter(c => c.group === group).map(c => c.key);
    const allSelected = groupColumns.every(k => selectedColumns.includes(k));
    
    if (allSelected) {
      setSelectedColumns(prev => prev.filter(k => !groupColumns.includes(k)));
    } else {
      setSelectedColumns(prev => [...new Set([...prev, ...groupColumns])]);
    }
  }, [selectedColumns]);

  // 현재 선택된 컬럼 (고정 + 선택된 컬럼)
  const displayColumns = [
    ...FIXED_COLUMNS,
    ...SELECTABLE_COLUMNS.filter(c => selectedColumns.includes(c.key))
  ];

  // 피험자 목록 로드
  useEffect(() => {
    loadSubjects();
  }, []);

  async function loadSubjects() {
    try {
      setLoadingSubjects(true);
      const token = getAuthToken();
      const response = await fetch('/api/subjects?page_size=100', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to load subjects');
      const data = await response.json();
      
      const options: SubjectOption[] = data.items.map((s: any) => ({
        id: s.id,
        name: s.encrypted_name || s.name || s.research_id,
        research_id: s.research_id,
      }));
      console.log('Loaded subjects:', options.length, 'Sample:', options[0]);
      setSubjects(options);
      
      // 테스트 목록도 같이 로드
      await loadAllTests();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoadingSubjects(false);
    }
  }

  // 전체 테스트 목록 로드
  async function loadAllTests() {
    try {
      setLoadingTests(true);
      const token = getAuthToken();
      const response = await fetch('/api/tests?page_size=100', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to load tests');
      const data = await response.json();
      
      console.log('Loaded tests:', data.items?.length, 'Sample:', data.items?.[0]);
      
      const options: TestOption[] = data.items.map((t: any) => ({
        test_id: t.test_id,
        source_filename: t.source_filename || 'Unknown',
        test_date: t.test_date,
        subject_id: t.subject_id,
        subject_name: t.subject_name,
      }));
      setTests(options);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoadingTests(false);
    }
  }

  // 피험자 선택 시 해당 피험자의 테스트만 필터
  useEffect(() => {
    if (selectedSubjectId) {
      // UUID 문자열 비교 (대소문자 무시)
      const filtered = tests.filter(t => 
        String(t.subject_id).toLowerCase() === String(selectedSubjectId).toLowerCase()
      );
      console.log('Filtering tests for subject:', selectedSubjectId, 'Found:', filtered.length, 'of', tests.length);
      setFilteredTests(filtered);
      setSelectedTestId('');
      setRawData(null);
    } else {
      setFilteredTests([]);
      setSelectedTestId('');
      setRawData(null);
    }
  }, [selectedSubjectId, tests]);

  // 선택한 테스트의 raw data 로드
  async function loadRawData() {
    if (!selectedTestId) return;
    
    try {
      setLoading(true);
      const token = getAuthToken();
      const response = await fetch(`/api/tests/${selectedTestId}/raw-data`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to load raw data');
      }
      const data: RawDataResponse = await response.json();
      setRawData(data);
      setCurrentPage(1);
    } catch (error) {
      toast.error(getErrorMessage(error));
      setRawData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (selectedTestId) {
      loadRawData();
    }
  }, [selectedTestId]);

  // 페이지네이션
  const totalPages = rawData ? Math.ceil(rawData.data.length / PAGE_SIZE) : 0;
  const paginatedData = rawData 
    ? rawData.data.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
    : [];

  // CSV 다운로드
  function downloadCSV() {
    if (!rawData) return;
    
    const headers = displayColumns.map(c => c.label).join(',');
    const rows = rawData.data.map(row => 
      displayColumns.map(col => {
        const value = (row as any)[col.key];
        return value ?? '';
      }).join(',')
    );
    
    const csv = [headers, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${rawData.source_filename || 'raw_data'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('CSV 다운로드 완료 (선택된 컬럼만)');
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="raw-data" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-full mx-auto px-6 pt-6">
        {/* 필터 영역 - 피험자 & 테스트 날짜 선택 */}
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 shadow-sm">
          <div className="flex gap-4 items-center flex-wrap">
            {/* 피험자 선택 */}
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-gray-500" />
              <label className="text-sm font-medium text-gray-700">피험자</label>
              <select
                className="px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2563EB] text-sm min-w-[200px]"
                value={selectedSubjectId}
                onChange={(e) => setSelectedSubjectId(e.target.value)}
                disabled={loadingSubjects}
              >
                <option value="">피험자 선택...</option>
                {loadingSubjects ? (
                  <option disabled>로딩중...</option>
                ) : subjects.length === 0 ? (
                  <option disabled>등록된 피험자 없음</option>
                ) : (
                  subjects.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.research_id})
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* 테스트 날짜 선택 */}
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-gray-500" />
              <label className="text-sm font-medium text-gray-700">테스트</label>
              <select
                className="px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2563EB] text-sm min-w-[300px] disabled:bg-gray-100"
                value={selectedTestId}
                onChange={(e) => setSelectedTestId(e.target.value)}
                disabled={!selectedSubjectId || loadingTests}
              >
                {!selectedSubjectId ? (
                  <option value="">피험자를 먼저 선택하세요</option>
                ) : filteredTests.length === 0 ? (
                  <option value="">테스트 없음</option>
                ) : (
                  <>
                    <option value="">테스트 선택...</option>
                    {filteredTests.map((t) => (
                      <option key={t.test_id} value={t.test_id}>
                        {new Date(t.test_date).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })} - {t.source_filename}
                      </option>
                    ))}
                  </>
                )}
              </select>
            </div>

            {/* CSV 다운로드 */}
            <Button variant="outline" size="sm" onClick={downloadCSV} disabled={!rawData} className="ml-auto">
              <Download className="w-4 h-4 mr-1" />
              CSV
            </Button>
          </div>
          
          {/* 선택된 정보 표시 */}
          {rawData && (
            <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-4 text-sm text-gray-600">
              <span className="font-medium text-gray-900">{rawData.source_filename}</span>
              <span>피험자: {rawData.subject_name || 'Unknown'}</span>
              <span>날짜: {new Date(rawData.test_date).toLocaleDateString()}</span>
              <span>총 {rawData.total_rows.toLocaleString()}행</span>
              <span>표시 컬럼: {displayColumns.length}개</span>
            </div>
          )}
        </div>

        {/* 데이터 테이블 */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : rawData ? (
          <Card>
            <CardHeader className="py-3">
              <div className="flex justify-between items-center">
                <CardTitle className="text-base flex items-center gap-2">
                  <Database className="w-4 h-4" />
                  Breath Data
                </CardTitle>
                <div className="flex items-center gap-2">
                  {/* 컬럼 선택기 */}
                  <div className="relative" ref={columnSelectorRef}>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowColumnSelector(!showColumnSelector)}
                      className="gap-1"
                    >
                      <Settings2 className="w-4 h-4" />
                      컬럼 선택
                    </Button>
                    
                    {showColumnSelector && (
                      <div className="absolute right-0 top-full mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                        <div className="p-3 border-b bg-gray-50">
                          <div className="flex justify-between items-center">
                            <span className="font-medium text-sm">표시할 컬럼 선택</span>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setSelectedColumns(DEFAULT_SELECTED_COLUMNS)}
                              className="text-xs h-6 px-2"
                            >
                              기본값
                            </Button>
                          </div>
                        </div>
                        
                        {(Object.keys(COLUMN_GROUPS) as Array<keyof typeof COLUMN_GROUPS>).map(group => {
                          const groupColumns = SELECTABLE_COLUMNS.filter(c => c.group === group);
                          const allSelected = groupColumns.every(c => selectedColumns.includes(c.key));
                          const someSelected = groupColumns.some(c => selectedColumns.includes(c.key));
                          
                          return (
                            <div key={group} className="border-b last:border-b-0">
                              <div 
                                className="flex items-center gap-2 p-2 bg-gray-50 cursor-pointer hover:bg-gray-100"
                                onClick={() => toggleGroup(group)}
                              >
                                <div className={`w-4 h-4 rounded border flex items-center justify-center ${
                                  allSelected ? 'bg-[#2563EB] border-[#2563EB]' : 
                                  someSelected ? 'bg-[#2563EB]/50 border-[#2563EB]' : 'border-gray-300'
                                }`}>
                                  {allSelected && <Check className="w-3 h-3 text-white" />}
                                </div>
                                <span className={`px-2 py-0.5 text-xs rounded ${COLUMN_GROUPS[group].color}`}>
                                  {COLUMN_GROUPS[group].label}
                                </span>
                                <span className="text-xs text-gray-500">
                                  ({groupColumns.filter(c => selectedColumns.includes(c.key)).length}/{groupColumns.length})
                                </span>
                              </div>
                              <div className="px-3 py-2 grid grid-cols-2 gap-1">
                                {groupColumns.map(col => (
                                  <label 
                                    key={col.key} 
                                    className="flex items-center gap-2 py-1 px-2 rounded hover:bg-gray-50 cursor-pointer text-sm"
                                  >
                                    <input
                                      type="checkbox"
                                      checked={selectedColumns.includes(col.key)}
                                      onChange={() => toggleColumn(col.key)}
                                      className="w-3.5 h-3.5 rounded border-gray-300 text-[#2563EB] focus:ring-[#2563EB]"
                                    />
                                    {col.label}
                                  </label>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  
                  <div className="w-px h-6 bg-gray-300" />
                  
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-gray-600">
                    {currentPage} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {/* 고정 컬럼 + 스크롤 가능 테이블 */}
              <div className="flex">
                {/* 왼쪽 고정 컬럼 (#, Time, Phase) */}
                <div className="flex-shrink-0 border-r border-gray-200 bg-white z-10 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.1)]">
                  <table className="text-sm">
                    <thead>
                      <tr className="border-b bg-gray-50">
                        <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">#</th>
                        {FIXED_COLUMNS.map(col => (
                          <th key={col.key} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">
                            {col.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedData.map((row, idx) => (
                        <tr key={row.id} className="border-b hover:bg-gray-50">
                          <td className="px-3 py-1.5 text-gray-400 whitespace-nowrap">
                            {(currentPage - 1) * PAGE_SIZE + idx + 1}
                          </td>
                          {FIXED_COLUMNS.map(col => (
                            <td key={col.key} className="px-3 py-1.5 text-gray-900 font-mono text-xs whitespace-nowrap">
                              {col.format((row as any)[col.key])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                
                {/* 오른쪽 스크롤 가능 영역 */}
                <div className="overflow-x-auto flex-1">
                  <table className="text-sm w-full">
                    <thead>
                      <tr className="border-b bg-gray-50">
                        {SELECTABLE_COLUMNS.filter(c => selectedColumns.includes(c.key)).map(col => (
                          <th key={col.key} className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">
                            <span className="flex items-center gap-1">
                              {col.label}
                              <span className={`w-2 h-2 rounded-full ${
                                col.group === 'basic' ? 'bg-blue-400' :
                                col.group === 'respiratory' ? 'bg-green-400' :
                                col.group === 'metabolic' ? 'bg-orange-400' :
                                'bg-purple-400'
                              }`} title={COLUMN_GROUPS[col.group as keyof typeof COLUMN_GROUPS].label} />
                            </span>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedData.map((row) => (
                        <tr key={row.id} className="border-b hover:bg-gray-50">
                          {SELECTABLE_COLUMNS.filter(c => selectedColumns.includes(c.key)).map(col => (
                            <td key={col.key} className="px-3 py-1.5 text-gray-900 font-mono text-xs whitespace-nowrap">
                              {col.format((row as any)[col.key])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="p-12 text-center text-gray-400">
            <Database className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-lg font-medium text-gray-500">피험자와 테스트를 선택하세요</p>
            <p className="text-sm mt-1">상단 필터에서 피험자를 먼저 선택한 후, 테스트 날짜를 선택하면 데이터가 표시됩니다.</p>
          </Card>
        )}
      </div>
    </div>
  );
}
