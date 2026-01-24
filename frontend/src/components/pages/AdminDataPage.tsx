import { useEffect, useState } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Database, ExternalLink, CheckCircle, XCircle, Activity, Filter, Edit, Save, X as XIcon, CheckCircle2, CircleDashed } from 'lucide-react';
import { api, type AdminStats } from '@/lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '@/utils/apiHelpers';

interface AdminDataPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

interface TestValidationInfo {
  is_valid: boolean;
  protocol_type: string;
  quality_score: number;
  duration_min: number;
  max_power: number;
  hr_dropout_rate: number;
  gas_dropout_rate: number;
  power_time_correlation?: number;
  issues: string[];
}

interface AdminTestRow {
  test_id: string;
  test_date: string;
  test_time?: string;
  subject_id: string;
  subject_name: string;
  subject_age?: number;
  height_cm?: number;
  weight_kg?: number;
  protocol_type?: string;
  source_filename?: string;
  parsing_status?: string;
  validation: TestValidationInfo;
  vo2_max?: number;
  fat_max_watt?: number;
  // Processing status (denormalized from processed_metabolism)
  processing_status?: 'none' | 'complete';
  last_analysis_version?: string;
  analysis_saved_at?: string;
}

interface AdminTestListResponse {
  items: AdminTestRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export function AdminDataPage({ user, onLogout, onNavigate }: AdminDataPageProps) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [tests, setTests] = useState<AdminTestListResponse | null>(null);
  const [testsLoading, setTestsLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [filterProtocol, setFilterProtocol] = useState<string>('');
  const [filterValid, setFilterValid] = useState<string>('');
  const [showTable, setShowTable] = useState(false);

  // 편집 상태
  const [editingTestId, setEditingTestId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<{
    age?: number;
    height_cm?: number;
    weight_kg?: number;
  }>({});

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (showTable) {
      loadTests();
    }
  }, [currentPage, filterProtocol, filterValid, showTable]);

  async function load() {
    try {
      setLoading(true);
      const response = await api.adminGetStats();
      setStats(response);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadTests() {
    try {
      setTestsLoading(true);
      const params = new URLSearchParams({
        page: currentPage.toString(),
        page_size: '20',
      });
      if (filterProtocol) params.append('protocol_type', filterProtocol);
      if (filterValid) params.append('is_valid', filterValid);

      const token = localStorage.getItem('access_token');
      if (!token) {
        throw new Error('No access token found. Please login again.');
      }

      const response = await fetch(`/api/admin/tests?${params.toString()}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to load tests' }));
        throw new Error(errorData.detail || 'Failed to load tests');
      }
      const data = await response.json();
      setTests(data);
    } catch (error) {
      console.error('Load tests error:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setTestsLoading(false);
    }
  }

  function startEdit(test: AdminTestRow) {
    setEditingTestId(test.test_id);
    setEditValues({
      age: test.subject_age || undefined,
      height_cm: test.height_cm || undefined,
      weight_kg: test.weight_kg || undefined,
    });
  }

  function cancelEdit() {
    setEditingTestId(null);
    setEditValues({});
  }

  async function saveEdit(testId: string) {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        throw new Error('No access token found');
      }

      const response = await fetch(`/api/admin/tests/${testId}/demographics`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(editValues)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to update' }));
        throw new Error(errorData.detail || 'Failed to update');
      }

      toast.success('정보가 업데이트되었습니다');
      setEditingTestId(null);
      setEditValues({});

      // Reload tests
      await loadTests();
    } catch (error) {
      console.error('Update error:', error);
      toast.error(getErrorMessage(error));
    }
  }

  function getProtocolIcon(protocol: string) {
    switch (protocol) {
      case 'RAMP': return '📈';
      case 'INTERVAL': return '📊';
      case 'STEADY_STATE': return '📉';
      default: return '❓';
    }
  }

  function getQualityColor(score: number) {
    if (score >= 0.95) return 'text-green-600';
    if (score >= 0.80) return 'text-blue-600';
    if (score >= 0.60) return 'text-yellow-600';
    return 'text-red-600';
  }

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleDateString('ko-KR');
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="admin-data" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Database className="w-6 h-6 text-[#2563EB]" />
              <h1 className="text-3xl font-bold text-gray-900">DB 관리</h1>
            </div>
            <p className="text-gray-600">데이터 현황 확인 및 운영 바로가기</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onNavigate('admin-dashboard')}>대시보드</Button>
            <Button variant="outline" onClick={load}>새로고침</Button>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">전체 사용자</p>
                  <p className="text-3xl font-bold text-gray-900">{stats?.users_total ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">피험자</p>
                  <p className="text-3xl font-bold text-gray-900">{stats?.subjects_total ?? 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-gray-600 mb-1">테스트</p>
                  <p className="text-3xl font-bold text-gray-900">{stats?.tests_total ?? 0}</p>
                </CardContent>
              </Card>
            </div>

            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-2">운영 링크</h2>
              <p className="text-sm text-gray-600 mb-4">기존 기능(피험자/테스트/분석)으로 바로 이동합니다.</p>
              <div className="flex gap-2 flex-wrap">
                <Button variant="outline" className="gap-2" onClick={() => onNavigate('subject-list')}>
                  피험자 관리
                  <ExternalLink className="w-4 h-4" />
                </Button>
                <Button variant="outline" className="gap-2" onClick={() => onNavigate('cohort-analysis')}>
                  코호트 분석
                  <ExternalLink className="w-4 h-4" />
                </Button>
                <Button variant="outline" className="gap-2" onClick={() => onNavigate('metabolism')}>
                  메타볼리즘
                  <ExternalLink className="w-4 h-4" />
                </Button>
              </div>
            </Card>

            {/* 전체 테스트 관리 테이블 */}
            <Card className="p-6 mt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-1">전체 테스트 데이터</h2>
                  <p className="text-sm text-gray-600">데이터 소스 현황 및 검증 상태</p>
                </div>
                <Button 
                  className="bg-[#2563EB]" 
                  onClick={() => setShowTable(!showTable)}
                >
                  {showTable ? '테이블 숨기기' : '테이블 보기'}
                </Button>
              </div>

              {showTable && (
                <>
                  {/* 필터 */}
                  <div className="flex gap-2 mb-4 flex-wrap">
                    <div className="flex items-center gap-2">
                      <Filter className="w-4 h-4 text-gray-500" />
                      <select 
                        className="px-3 py-1 border border-gray-300 rounded-md text-sm"
                        value={filterProtocol}
                        onChange={(e) => {
                          setFilterProtocol(e.target.value);
                          setCurrentPage(1);
                        }}
                      >
                        <option value="">모든 프로토콜</option>
                        <option value="RAMP">RAMP</option>
                        <option value="INTERVAL">INTERVAL</option>
                        <option value="STEADY_STATE">STEADY_STATE</option>
                        <option value="UNKNOWN">UNKNOWN</option>
                      </select>
                      
                      <select 
                        className="px-3 py-1 border border-gray-300 rounded-md text-sm"
                        value={filterValid}
                        onChange={(e) => {
                          setFilterValid(e.target.value);
                          setCurrentPage(1);
                        }}
                      >
                        <option value="">모든 유효성</option>
                        <option value="true">유효</option>
                        <option value="false">무효</option>
                      </select>

                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => {
                          setFilterProtocol('');
                          setFilterValid('');
                          setCurrentPage(1);
                        }}
                      >
                        초기화
                      </Button>
                    </div>
                  </div>

                  {testsLoading ? (
                    <div className="flex justify-center py-12">
                      <div className="w-8 h-8 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
                    </div>
                  ) : tests && tests.items.length > 0 ? (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead className="bg-gray-50 border-b">
                            <tr>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">피험자</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">나이</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">키</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">체중</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">수행일</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">프로토콜</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">길이</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">최대파워</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">품질</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">유효성</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">분석</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">파일명</th>
                              <th className="px-4 py-3 text-left font-medium text-gray-700">편집</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y">
                            {tests.items.map((test) => {
                              const isEditing = editingTestId === test.test_id;

                              return (
                                <tr key={test.test_id} className="hover:bg-gray-50">
                                  <td className="px-4 py-3">{test.subject_name}</td>

                                  {/* 나이 */}
                                  <td className="px-4 py-3 text-gray-600">
                                    {isEditing ? (
                                      <input
                                        type="number"
                                        className="w-20 px-2 py-1 border rounded text-sm"
                                        value={editValues.age || ''}
                                        onChange={(e) => setEditValues({ ...editValues, age: parseFloat(e.target.value) || undefined })}
                                        placeholder="나이"
                                      />
                                    ) : (
                                      test.subject_age ? `${test.subject_age}세` : '-'
                                    )}
                                  </td>

                                  {/* 키 */}
                                  <td className="px-4 py-3 text-gray-600">
                                    {isEditing ? (
                                      <input
                                        type="number"
                                        step="0.1"
                                        className="w-20 px-2 py-1 border rounded text-sm"
                                        value={editValues.height_cm || ''}
                                        onChange={(e) => setEditValues({ ...editValues, height_cm: parseFloat(e.target.value) || undefined })}
                                        placeholder="cm"
                                      />
                                    ) : (
                                      test.height_cm ? `${test.height_cm.toFixed(1)}cm` : '-'
                                    )}
                                  </td>

                                  {/* 체중 */}
                                  <td className="px-4 py-3 text-gray-600">
                                    {isEditing ? (
                                      <input
                                        type="number"
                                        step="0.1"
                                        className="w-20 px-2 py-1 border rounded text-sm"
                                        value={editValues.weight_kg || ''}
                                        onChange={(e) => setEditValues({ ...editValues, weight_kg: parseFloat(e.target.value) || undefined })}
                                        placeholder="kg"
                                      />
                                    ) : (
                                      test.weight_kg ? `${test.weight_kg.toFixed(1)}kg` : '-'
                                    )}
                                  </td>

                                  <td className="px-4 py-3 text-gray-600">
                                    {formatDate(test.test_date)}
                                  </td>
                                <td className="px-4 py-3">
                                  <span className="inline-flex items-center gap-1">
                                    {getProtocolIcon(test.validation.protocol_type)}
                                    <span className="text-xs font-medium">
                                      {test.validation.protocol_type}
                                    </span>
                                  </span>
                                </td>
                                <td className="px-4 py-3 text-gray-600">
                                  {test.validation.duration_min.toFixed(1)}분
                                </td>
                                <td className="px-4 py-3 text-gray-600">
                                  {test.validation.max_power > 0 
                                    ? `${test.validation.max_power.toFixed(0)}W`
                                    : '-'
                                  }
                                </td>
                                <td className="px-4 py-3">
                                  <span className={`font-medium ${getQualityColor(test.validation.quality_score)}`}>
                                    {test.validation.quality_score.toFixed(2)}
                                  </span>
                                </td>
                                <td className="px-4 py-3">
                                  {test.validation.is_valid ? (
                                    <span className="inline-flex items-center gap-1 text-green-600">
                                      <CheckCircle className="w-4 h-4" />
                                      <span className="text-xs font-medium">유효</span>
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 text-red-600">
                                      <XCircle className="w-4 h-4" />
                                      <span className="text-xs font-medium">무효</span>
                                    </span>
                                  )}
                                </td>
                                {/* 분석 상태 */}
                                <td className="px-4 py-3">
                                  {test.processing_status === 'complete' ? (
                                    <span
                                      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-green-50 text-green-700 border border-green-200 rounded-full"
                                      title={test.analysis_saved_at ? `저장: ${new Date(test.analysis_saved_at).toLocaleString('ko-KR')}` : undefined}
                                    >
                                      <CheckCircle2 className="w-3 h-3" />
                                      v{test.last_analysis_version || '1.0.0'}
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 rounded-full">
                                      <CircleDashed className="w-3 h-3" />
                                      Raw
                                    </span>
                                  )}
                                </td>
                                <td className="px-4 py-3 text-xs text-gray-500 max-w-xs truncate">
                                  {test.source_filename || '-'}
                                </td>

                                {/* 편집 버튼 */}
                                <td className="px-4 py-3">
                                  {isEditing ? (
                                    <div className="flex gap-1">
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => saveEdit(test.test_id)}
                                        className="text-green-600 hover:text-green-700 hover:bg-green-50"
                                      >
                                        <Save className="w-4 h-4" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={cancelEdit}
                                        className="text-gray-600 hover:text-gray-700 hover:bg-gray-100"
                                      >
                                        <XIcon className="w-4 h-4" />
                                      </Button>
                                    </div>
                                  ) : (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => startEdit(test)}
                                      className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                                    >
                                      <Edit className="w-4 h-4" />
                                    </Button>
                                  )}
                                </td>
                              </tr>
                            );
                            })}
                          </tbody>
                        </table>
                      </div>

                      {/* 페이지네이션 */}
                      <div className="flex items-center justify-between mt-4 pt-4 border-t">
                        <div className="text-sm text-gray-600">
                          총 {tests.total}개 테스트 (페이지 {tests.page} / {tests.total_pages})
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={currentPage === 1}
                            onClick={() => setCurrentPage(currentPage - 1)}
                          >
                            이전
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={currentPage >= tests.total_pages}
                            onClick={() => setCurrentPage(currentPage + 1)}
                          >
                            다음
                          </Button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-12 text-gray-500">
                      테스트 데이터가 없습니다.
                    </div>
                  )}
                </>
              )}
            </Card>

            <Card className="p-6 mt-6 border-red-200">
              <h2 className="text-lg font-semibold text-red-700 mb-2">Danger Zone</h2>
              <p className="text-sm text-gray-600">
                데이터 삭제/초기화 같은 위험 작업은 아직 UI로 제공하지 않습니다. 필요하면 요구사항에 맞춰
                개발환경 전용(예: DEBUG=true)으로 안전장치(confirm string) 포함해서 추가할 수 있어요.
              </p>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
