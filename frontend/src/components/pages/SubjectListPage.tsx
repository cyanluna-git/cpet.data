import { useState, useEffect } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Users, Search, UserPlus } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';

interface SubjectListPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

export function SubjectListPage({ user, onLogout, onNavigate }: SubjectListPageProps) {
  const [subjects, setSubjects] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSubjects();
  }, []);

  async function loadSubjects() {
    try {
      const data = await api.getSubjects();
      setSubjects(data);
    } catch (error) {
      console.error('Failed to load subjects:', error);
      toast.error('피험자 목록 로딩 실패');
    } finally {
      setLoading(false);
    }
  }

  const filteredSubjects = subjects.filter(s =>
    s && (
      s.research_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.name?.toLowerCase().includes(searchTerm.toLowerCase())
    )
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="subject-list" onNavigate={onNavigate} onLogout={onLogout} />
      
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">피험자 관리</h1>
            <p className="text-gray-600">등록된 피험자를 관리하고 검사 기록을 확인하세요.</p>
          </div>
          <Button className="bg-[#2563EB] gap-2" onClick={() => toast.info('피험자 등록 기능은 곧 추가됩니다')}>
            <UserPlus className="w-4 h-4" />
            피험자 등록
          </Button>
        </div>

        {/* Search */}
        <div className="mb-6">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <Input
              placeholder="피험자 ID 또는 이름으로 검색..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 h-12"
            />
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">전체 피험자</p>
              <p className="text-3xl font-bold text-gray-900">{subjects.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">남성</p>
              <p className="text-3xl font-bold text-[#2563EB]">
                {subjects.filter(s => s.gender === 'M').length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">여성</p>
              <p className="text-3xl font-bold text-[#F97316]">
                {subjects.filter(s => s.gender === 'F').length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">평균 연령</p>
              <p className="text-3xl font-bold text-gray-900">
                {subjects.length > 0 ? Math.round(subjects.reduce((acc, s) => acc + (new Date().getFullYear() - s.birth_year), 0) / subjects.length) : 0}세
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Subject List */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : filteredSubjects.length === 0 ? (
          <Card className="p-12 text-center">
            <Users className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">피험자가 없습니다</h3>
            <p className="text-gray-600 mb-6">첫 번째 피험자를 등록하세요.</p>
            <Button className="bg-[#2563EB]" onClick={() => toast.info('피험자 등록 기능은 곧 추가됩니다')}>
              <UserPlus className="w-4 h-4 mr-2" />
              피험자 등록
            </Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredSubjects.map((subject) => (
              <Card
                key={subject.id}
                className="hover:shadow-lg transition-shadow cursor-pointer"
                onClick={() => onNavigate('subject-detail', { subjectId: subject.id })}
              >
                <CardContent className="pt-6">
                  <div className="flex items-start gap-4">
                    <div className="w-16 h-16 bg-gradient-to-br from-[#2563EB] to-[#3B82F6] rounded-full flex items-center justify-center text-white font-bold text-2xl flex-shrink-0">
                      {subject.name?.charAt(0) || subject.research_id?.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-bold text-gray-900 text-lg mb-1 truncate">
                        {subject.research_id}
                      </h3>
                      <div className="flex flex-wrap gap-2 mb-3">
                        <Badge variant="outline" className="text-xs">
                          {subject.gender === 'M' ? '남성' : '여성'}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {new Date().getFullYear() - subject.birth_year}세
                        </Badge>
                        {subject.training_level && (
                          <Badge variant="secondary" className="text-xs">
                            {subject.training_level}
                          </Badge>
                        )}
                      </div>
                      <div className="text-sm text-gray-600 space-y-1">
                        <p>키: {subject.height_cm}cm · 체중: {subject.weight_kg}kg</p>
                        {subject.created_at && (
                          <p className="text-xs text-gray-500">
                            등록: {new Date(subject.created_at).toLocaleDateString('ko-KR')}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}