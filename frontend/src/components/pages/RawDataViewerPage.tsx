import { useEffect, useState } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, Database, Download, ChevronLeft, ChevronRight } from 'lucide-react';
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
  subject_name?: string;
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

// 표시할 컬럼 정의
const COLUMNS = [
  { key: 't_sec', label: 'Time(s)', format: (v: number | null) => v?.toFixed(0) ?? '-' },
  { key: 'phase', label: 'Phase', format: (v: string | null) => v ?? '-' },
  { key: 'hr', label: 'HR', format: (v: number | null) => v ?? '-' },
  { key: 'vo2', label: 'VO2', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'vco2', label: 'VCO2', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 've', label: 'VE', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'rer', label: 'RER', format: (v: number | null) => v?.toFixed(2) ?? '-' },
  { key: 'fat_oxidation', label: 'Fat(g/min)', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'cho_oxidation', label: 'CHO(g/min)', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'bike_power', label: 'Power(W)', format: (v: number | null) => v ?? '-' },
  { key: 'cadence', label: 'Cadence', format: (v: number | null) => v ?? '-' },
  { key: 'rf', label: 'RF', format: (v: number | null) => v?.toFixed(1) ?? '-' },
  { key: 'vt', label: 'VT', format: (v: number | null) => v?.toFixed(3) ?? '-' },
  { key: 'mets', label: 'METs', format: (v: number | null) => v?.toFixed(1) ?? '-' },
];

const PAGE_SIZE = 50;

export function RawDataViewerPage({ user, onLogout, onNavigate }: RawDataViewerPageProps) {
  const [tests, setTests] = useState<TestOption[]>([]);
  const [selectedTestId, setSelectedTestId] = useState<string>('');
  const [rawData, setRawData] = useState<RawDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingTests, setLoadingTests] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);

  // 테스트 목록 로드
  useEffect(() => {
    loadTests();
  }, []);

  async function loadTests() {
    try {
      setLoadingTests(true);
      const token = getAuthToken();
      const response = await fetch('/api/tests?page_size=100', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to load tests');
      const data = await response.json();
      
      const options: TestOption[] = data.items.map((t: any) => ({
        test_id: t.test_id,
        source_filename: t.source_filename || 'Unknown',
        test_date: t.test_date,
        subject_name: t.subject_name,
      }));
      setTests(options);
      
      if (options.length > 0) {
        setSelectedTestId(options[0].test_id);
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoadingTests(false);
    }
  }

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
    
    const headers = COLUMNS.map(c => c.label).join(',');
    const rows = rawData.data.map(row => 
      COLUMNS.map(col => {
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
    toast.success('CSV 다운로드 완료');
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="raw-data" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-full mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Database className="w-6 h-6 text-[#2563EB]" />
              <h1 className="text-3xl font-bold text-gray-900">Raw Data Viewer</h1>
            </div>
            <p className="text-gray-600">테스트별 호흡 데이터 (breath_data) 원본 조회</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onNavigate('admin-data')}>
              DB 관리
            </Button>
          </div>
        </div>

        {/* 테스트 선택 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Table className="w-5 h-5" />
              테스트 선택
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  테스트
                </label>
                <select
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#2563EB]"
                  value={selectedTestId}
                  onChange={(e) => setSelectedTestId(e.target.value)}
                  disabled={loadingTests}
                >
                  {loadingTests ? (
                    <option>로딩중...</option>
                  ) : tests.length === 0 ? (
                    <option>테스트 없음</option>
                  ) : (
                    tests.map((t) => (
                      <option key={t.test_id} value={t.test_id}>
                        {t.source_filename} ({new Date(t.test_date).toLocaleDateString()})
                      </option>
                    ))
                  )}
                </select>
              </div>
              <Button onClick={loadRawData} disabled={loading || !selectedTestId}>
                {loading ? '로딩중...' : '조회'}
              </Button>
              <Button variant="outline" onClick={downloadCSV} disabled={!rawData}>
                <Download className="w-4 h-4 mr-2" />
                CSV
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 데이터 테이블 */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : rawData ? (
          <Card>
            <CardHeader>
              <div className="flex justify-between items-center">
                <div>
                  <CardTitle>{rawData.source_filename}</CardTitle>
                  <p className="text-sm text-gray-500 mt-1">
                    피험자: {rawData.subject_name || 'Unknown'} | 
                    날짜: {new Date(rawData.test_date).toLocaleDateString()} |
                    총 {rawData.total_rows}행
                  </p>
                </div>
                <div className="flex items-center gap-2">
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
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="px-2 py-2 text-left font-medium text-gray-600">#</th>
                    {COLUMNS.map(col => (
                      <th key={col.key} className="px-2 py-2 text-left font-medium text-gray-600">
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedData.map((row, idx) => (
                    <tr key={row.id} className="border-b hover:bg-gray-50">
                      <td className="px-2 py-1.5 text-gray-400">
                        {(currentPage - 1) * PAGE_SIZE + idx + 1}
                      </td>
                      {COLUMNS.map(col => (
                        <td key={col.key} className="px-2 py-1.5 text-gray-900 font-mono text-xs">
                          {col.format((row as any)[col.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        ) : (
          <Card className="p-12 text-center text-gray-500">
            테스트를 선택하고 조회 버튼을 클릭하세요
          </Card>
        )}
      </div>
    </div>
  );
}
