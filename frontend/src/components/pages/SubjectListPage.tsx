import { useState, useEffect } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Users, Search, UserPlus, Pencil, Eye, X, Save, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { extractItems, getErrorMessage } from '@/utils/apiHelpers';

interface SubjectListPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

const GENDER_OPTIONS = [
  { value: 'none', label: '선택 안함' },
  { value: 'M', label: '남성' },
  { value: 'F', label: '여성' },
];

const TRAINING_LEVELS = [
  { value: 'Sedentary', label: '비활동적 (Sedentary)' },
  { value: 'Recreational', label: '취미 수준 (Recreational)' },
  { value: 'Trained', label: '훈련됨 (Trained)' },
  { value: 'Elite', label: '엘리트 (Elite)' },
];

const JOB_CATEGORIES = [
  { value: 'none', label: '선택 안함' },
  { value: '사무직', label: '사무직' },
  { value: '현장직', label: '현장직' },
  { value: '운동선수', label: '운동선수' },
  { value: '학생', label: '학생' },
  { value: '기타', label: '기타' },
];

export function SubjectListPage({ user, onLogout, onNavigate }: SubjectListPageProps) {
  const [subjects, setSubjects] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);

  // Edit modal state
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState<any>(null);
  const [editForm, setEditForm] = useState({
    gender: 'none',
    birth_year: '',
    height_cm: '',
    weight_kg: '',
    body_fat_percent: '',
    skeletal_muscle_mass: '',
    bmi: '',
    training_level: 'none',
    job_category: 'none',
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSubjects();
  }, []);

  async function loadSubjects() {
    try {
      const response = await api.getSubjects();
      const subjectsData = extractItems(response);
      setSubjects(subjectsData);
    } catch (error) {
      console.error('Failed to load subjects:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  const filteredSubjects = subjects.filter(s =>
    s && (
      s.research_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.encrypted_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.training_level?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.job_category?.toLowerCase().includes(searchTerm.toLowerCase())
    )
  );

  function openEditModal(subject: any) {
    setEditingSubject(subject);
    setEditForm({
      gender: subject.gender || 'none',
      birth_year: subject.birth_year?.toString() || '',
      height_cm: subject.height_cm?.toString() || '',
      weight_kg: subject.weight_kg?.toString() || '',
      body_fat_percent: subject.body_fat_percent?.toString() || '',
      skeletal_muscle_mass: subject.skeletal_muscle_mass?.toString() || '',
      bmi: subject.bmi?.toString() || '',
      training_level: subject.training_level || 'none',
      job_category: subject.job_category || 'none',
      notes: subject.notes || '',
    });
    setEditModalOpen(true);
  }

  async function handleSaveEdit() {
    if (!editingSubject) return;

    setSaving(true);
    try {
      // Convert "none" back to undefined for API
      const gender = editForm.gender === 'none' ? undefined : editForm.gender;
      const trainingLevel = editForm.training_level === 'none' ? undefined : editForm.training_level;
      const jobCategory = editForm.job_category === 'none' ? undefined : editForm.job_category;
      const birthYear = editForm.birth_year ? parseInt(editForm.birth_year) : undefined;
      const heightCm = editForm.height_cm ? parseFloat(editForm.height_cm) : undefined;
      const weightKg = editForm.weight_kg ? parseFloat(editForm.weight_kg) : undefined;
      const bodyFatPercent = editForm.body_fat_percent ? parseFloat(editForm.body_fat_percent) : undefined;
      const skeletalMuscleMass = editForm.skeletal_muscle_mass ? parseFloat(editForm.skeletal_muscle_mass) : undefined;
      const bmi = editForm.bmi ? parseFloat(editForm.bmi) : undefined;

      await api.updateSubject(editingSubject.id, {
        gender: gender,
        birth_year: birthYear,
        height_cm: heightCm,
        weight_kg: weightKg,
        body_fat_percent: bodyFatPercent,
        skeletal_muscle_mass: skeletalMuscleMass,
        bmi: bmi,
        training_level: trainingLevel,
        job_category: jobCategory,
        notes: editForm.notes || undefined,
      });

      // Update local state with actual values
      setSubjects(prev =>
        prev.map(s =>
          s.id === editingSubject.id
            ? {
                ...s,
                gender: gender || null,
                birth_year: birthYear || null,
                height_cm: heightCm || null,
                weight_kg: weightKg || null,
                body_fat_percent: bodyFatPercent || null,
                skeletal_muscle_mass: skeletalMuscleMass || null,
                bmi: bmi || null,
                training_level: trainingLevel || null,
                job_category: jobCategory || null,
                notes: editForm.notes || null,
              }
            : s
        )
      );

      toast.success('피험자 정보가 수정되었습니다.');
      setEditModalOpen(false);
    } catch (error) {
      console.error('Failed to update subject:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  function formatBirthYearMonth(birthYear: number | null, birthDate: string | null): string | null {
    if (birthDate) {
      const date = new Date(birthDate);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      return `${year}.${month}`;
    }
    if (birthYear) {
      return `${birthYear}`;
    }
    return null;
  }

  function calculateAge(birthYear: number | null, birthDate: string | null): number | null {
    if (birthDate) {
      return new Date().getFullYear() - new Date(birthDate).getFullYear();
    }
    if (birthYear) {
      return new Date().getFullYear() - birthYear;
    }
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="subject-list" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">피험자 관리</h1>
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
              placeholder="피험자 ID, 이름, 훈련 수준으로 검색..."
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
              <p className="text-xl sm:text-2xl md:text-3xl font-bold text-gray-900">{subjects.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">남성</p>
              <p className="text-xl sm:text-2xl md:text-3xl font-bold text-[#2563EB]">
                {subjects.filter(s => s.gender === 'M').length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">여성</p>
              <p className="text-xl sm:text-2xl md:text-3xl font-bold text-[#F97316]">
                {subjects.filter(s => s.gender === 'F').length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-gray-600 mb-1">평균 연령</p>
              <p className="text-xl sm:text-2xl md:text-3xl font-bold text-gray-900">
                {subjects.length > 0
                  ? Math.round(
                      subjects.reduce((acc, s) => {
                        const age = calculateAge(s.birth_year, s.birth_date);
                        return acc + (age || 0);
                      }, 0) / subjects.filter(s => calculateAge(s.birth_year, s.birth_date)).length
                    ) || '-'
                  : '-'}세
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Subject Table */}
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
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="px-4 py-3 text-left font-medium text-gray-600">피험자 ID</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">이름</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">성별</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">생년월</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">신체</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">훈련 수준</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">직업</th>
                      <th className="px-4 py-3 text-left font-medium text-gray-600">메모</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">등록일</th>
                      <th className="px-4 py-3 text-center font-medium text-gray-600">액션</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSubjects.map((subject) => {
                      const birthYearMonth = formatBirthYearMonth(subject.birth_year, subject.birth_date);
                      return (
                        <tr
                          key={subject.id}
                          className="border-b hover:bg-gray-50 transition-colors"
                        >
                          <td className="px-4 py-3 font-mono font-medium text-gray-900">
                            {subject.research_id}
                          </td>
                          <td className="px-4 py-3 text-gray-700">
                            {subject.encrypted_name || '-'}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Badge
                              variant="outline"
                              className={subject.gender === 'M' ? 'border-blue-300 text-blue-700' : 'border-pink-300 text-pink-700'}
                            >
                              {subject.gender === 'M' ? '남' : subject.gender === 'F' ? '여' : '-'}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-center text-gray-700">
                            {birthYearMonth || '-'}
                          </td>
                          <td className="px-4 py-3 text-center text-gray-600 text-xs">
                            {subject.height_cm && subject.weight_kg
                              ? `${subject.height_cm}cm / ${subject.weight_kg}kg`
                              : '-'}
                          </td>
                          <td className="px-4 py-3">
                            {subject.training_level ? (
                              <Badge variant="secondary" className="text-xs">
                                {subject.training_level}
                              </Badge>
                            ) : (
                              <span className="text-gray-400 text-xs">미설정</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gray-600 text-xs">
                            {subject.job_category || '-'}
                          </td>
                          <td className="px-4 py-3">
                            {subject.notes ? (
                              <span className="text-gray-600 text-xs truncate max-w-[150px] block" title={subject.notes}>
                                {subject.notes.length > 20 ? subject.notes.slice(0, 20) + '...' : subject.notes}
                              </span>
                            ) : (
                              <span className="text-gray-400 text-xs">-</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-center text-gray-500 text-xs">
                            {subject.created_at
                              ? new Date(subject.created_at).toLocaleDateString('ko-KR')
                              : '-'}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <div className="flex items-center justify-center gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0"
                                onClick={() => onNavigate('subject-detail', { subjectId: subject.id })}
                                title="상세 보기"
                              >
                                <Eye className="w-4 h-4 text-gray-500" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openEditModal(subject);
                                }}
                                title="편집"
                              >
                                <Pencil className="w-4 h-4 text-blue-500" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Edit Modal */}
      <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
        <DialogContent className="sm:max-w-[550px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="w-5 h-5 text-blue-500" />
              피험자 정보 편집
            </DialogTitle>
            <DialogDescription>
              {editingSubject?.research_id} - {editingSubject?.encrypted_name || '이름 없음'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
            {/* Basic Info Row */}
            <div className="grid grid-cols-2 gap-4">
              {/* Gender */}
              <div className="space-y-2">
                <Label>성별</Label>
                <Select
                  value={editForm.gender}
                  onValueChange={(value) => setEditForm(prev => ({ ...prev, gender: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="성별 선택" />
                  </SelectTrigger>
                  <SelectContent>
                    {GENDER_OPTIONS.map(option => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Birth Year */}
              <div className="space-y-2">
                <Label>출생연도</Label>
                <Input
                  type="number"
                  placeholder="예: 1990"
                  value={editForm.birth_year}
                  onChange={(e) => setEditForm(prev => ({ ...prev, birth_year: e.target.value }))}
                  min={1900}
                  max={2100}
                />
              </div>
            </div>

            {/* Body Info Row */}
            <div className="grid grid-cols-2 gap-4">
              {/* Height */}
              <div className="space-y-2">
                <Label>키 (cm)</Label>
                <Input
                  type="number"
                  placeholder="예: 175"
                  value={editForm.height_cm}
                  onChange={(e) => setEditForm(prev => ({ ...prev, height_cm: e.target.value }))}
                  min={100}
                  max={250}
                  step="0.1"
                />
              </div>

              {/* Weight */}
              <div className="space-y-2">
                <Label>체중 (kg)</Label>
                <Input
                  type="number"
                  placeholder="예: 70"
                  value={editForm.weight_kg}
                  onChange={(e) => setEditForm(prev => ({ ...prev, weight_kg: e.target.value }))}
                  min={20}
                  max={300}
                  step="0.1"
                />
              </div>
            </div>

            {/* Body Composition Row */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Body Fat Percent */}
              <div className="space-y-2">
                <Label>체지방률 (%)</Label>
                <Input
                  type="number"
                  placeholder="예: 15.5"
                  value={editForm.body_fat_percent}
                  onChange={(e) => setEditForm(prev => ({ ...prev, body_fat_percent: e.target.value }))}
                  min={0}
                  max={100}
                  step="0.1"
                />
              </div>

              {/* Skeletal Muscle Mass */}
              <div className="space-y-2">
                <Label>골격근량 (kg)</Label>
                <Input
                  type="number"
                  placeholder="예: 32.5"
                  value={editForm.skeletal_muscle_mass}
                  onChange={(e) => setEditForm(prev => ({ ...prev, skeletal_muscle_mass: e.target.value }))}
                  min={0}
                  max={100}
                  step="0.1"
                />
              </div>

              {/* BMI */}
              <div className="space-y-2">
                <Label>BMI</Label>
                <Input
                  type="number"
                  placeholder="예: 22.5"
                  value={editForm.bmi}
                  onChange={(e) => setEditForm(prev => ({ ...prev, bmi: e.target.value }))}
                  min={10}
                  max={60}
                  step="0.1"
                />
              </div>
            </div>

            {/* Training Level */}
            <div className="space-y-2">
              <Label>훈련 수준</Label>
              <Select
                value={editForm.training_level}
                onValueChange={(value) => setEditForm(prev => ({ ...prev, training_level: value }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="훈련 수준 선택" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">선택 안함</SelectItem>
                  {TRAINING_LEVELS.map(level => (
                    <SelectItem key={level.value} value={level.value}>
                      {level.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Job Category */}
            <div className="space-y-2">
              <Label>직업 카테고리</Label>
              <Select
                value={editForm.job_category}
                onValueChange={(value) => setEditForm(prev => ({ ...prev, job_category: value }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="직업 선택" />
                </SelectTrigger>
                <SelectContent>
                  {JOB_CATEGORIES.map(job => (
                    <SelectItem key={job.value || 'none'} value={job.value}>
                      {job.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label>메모 / 라벨</Label>
              <Textarea
                placeholder="추가 메모나 라벨을 입력하세요..."
                value={editForm.notes}
                onChange={(e) => setEditForm(prev => ({ ...prev, notes: e.target.value }))}
                rows={3}
              />
              <p className="text-xs text-gray-500">
                예: 크로스핏 선수, 마라톤 대비 훈련 중, 재활 대상자 등
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditModalOpen(false)} disabled={saving}>
              <X className="w-4 h-4 mr-2" />
              취소
            </Button>
            <Button onClick={handleSaveEdit} disabled={saving} className="bg-[#2563EB]">
              {saving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              저장
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
