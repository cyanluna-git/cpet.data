import { useEffect, useMemo, useState } from 'react';
import { Navigation } from '@/components/layout/Navigation';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Search, UserPlus, Pencil, Trash2 } from 'lucide-react';
import { api, type AdminUser } from '@/lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '@/utils/apiHelpers';

interface AdminUsersPageProps {
  user: any;
  onLogout: () => void;
  onNavigate: (view: string, params?: any) => void;
}

function roleLabel(role: AdminUser['role']) {
  if (role === 'admin') return 'admin';
  if (role === 'researcher') return 'researcher';
  return 'subject';
}

function roleBadgeVariant(role: AdminUser['role']): 'default' | 'secondary' | 'outline' {
  if (role === 'admin') return 'default';
  if (role === 'researcher') return 'secondary';
  return 'outline';
}

export function AdminUsersPage({ user, onLogout, onNavigate }: AdminUsersPageProps) {
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState('');

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);

  const [formEmail, setFormEmail] = useState('');
  const [formPassword, setFormPassword] = useState('');
  const [formRole, setFormRole] = useState<'admin' | 'researcher' | 'subject'>('subject');
  const [formActive, setFormActive] = useState(true);

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    try {
      setLoading(true);
      const response = await api.adminListUsers({ search: search || undefined });
      setUsers(response.items);
    } catch (error) {
      console.error('Failed to load users:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    if (!search) return users;
    const s = search.toLowerCase();
    return users.filter(u => u.email.toLowerCase().includes(s));
  }, [users, search]);

  function openCreate() {
    setEditingUser(null);
    setFormEmail('');
    setFormPassword('');
    setFormRole('subject');
    setFormActive(true);
    setDialogOpen(true);
  }

  function openEdit(u: AdminUser) {
    setEditingUser(u);
    setFormEmail(u.email);
    setFormPassword('');
    setFormRole(u.role === 'user' ? 'subject' : u.role);
    setFormActive(u.is_active);
    setDialogOpen(true);
  }

  async function submitForm() {
    try {
      if (!formEmail.trim()) {
        toast.error('이메일을 입력해주세요');
        return;
      }

      if (!editingUser) {
        if (!formPassword || formPassword.length < 6) {
          toast.error('비밀번호는 6자 이상이어야 합니다');
          return;
        }
        await api.adminCreateUser({ email: formEmail.trim(), password: formPassword, role: formRole });
        toast.success('사용자가 생성되었습니다');
      } else {
        await api.adminUpdateUser(editingUser.user_id, {
          email: formEmail.trim(),
          password: formPassword ? formPassword : undefined,
          role: formRole,
          is_active: formActive,
        });
        toast.success('사용자가 업데이트되었습니다');
      }

      setDialogOpen(false);
      await loadUsers();
    } catch (error) {
      console.error('Failed to submit user form:', error);
      toast.error(getErrorMessage(error));
    }
  }

  async function toggleActive(u: AdminUser, next: boolean) {
    try {
      await api.adminUpdateUser(u.user_id, { is_active: next });
      setUsers(prev => prev.map(x => (x.user_id === u.user_id ? { ...x, is_active: next } : x)));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  async function deleteUser(u: AdminUser) {
    if (!confirm(`정말로 삭제할까요?\n${u.email}`)) return;
    try {
      await api.adminDeleteUser(u.user_id);
      toast.success('삭제되었습니다');
      setUsers(prev => prev.filter(x => x.user_id !== u.user_id));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Navigation user={user} currentView="admin-users" onNavigate={onNavigate} onLogout={onLogout} />

      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">사용자 관리</h1>
            <p className="text-gray-600">회원/권한/활성 상태를 관리합니다.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onNavigate('admin-dashboard')}>대시보드</Button>
            <Button className="bg-[#2563EB] gap-2" onClick={openCreate}>
              <UserPlus className="w-4 h-4" />
              사용자 생성
            </Button>
          </div>
        </div>

        <div className="mb-6">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <Input
              placeholder="이메일로 검색..."
              value={search}
              onChange={(e) => setSearchTermSafe(setSearch, e.target.value)}
              className="pl-10 h-12"
            />
          </div>
        </div>

        <Card>
          <CardContent className="pt-6">
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="w-16 h-16 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>이메일</TableHead>
                    <TableHead>역할</TableHead>
                    <TableHead>활성</TableHead>
                    <TableHead>마지막 로그인</TableHead>
                    <TableHead>생성일</TableHead>
                    <TableHead className="text-right">작업</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((u) => (
                    <TableRow key={u.user_id}>
                      <TableCell className="font-medium">{u.email}</TableCell>
                      <TableCell>
                        <Badge variant={roleBadgeVariant(u.role)} className="capitalize">
                          {roleLabel(u.role)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Switch checked={u.is_active} onCheckedChange={(v) => toggleActive(u, v)} />
                          <span className="text-xs text-gray-500">{u.is_active ? '활성' : '비활성'}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-gray-600">
                        {u.last_login ? new Date(u.last_login).toLocaleString() : '-'}
                      </TableCell>
                      <TableCell className="text-gray-600">
                        {u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="outline" size="sm" className="gap-1" onClick={() => openEdit(u)}>
                            <Pencil className="w-4 h-4" />
                            수정
                          </Button>
                          <Button variant="outline" size="sm" className="gap-1 text-red-600" onClick={() => deleteUser(u)}>
                            <Trash2 className="w-4 h-4" />
                            삭제
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {filtered.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="py-10 text-center text-gray-500">
                        사용자가 없습니다.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <span />
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingUser ? '사용자 수정' : '사용자 생성'}</DialogTitle>
              <DialogDescription>
                {editingUser ? '이메일/역할/활성 상태를 변경합니다. 비밀번호를 입력하면 재설정됩니다.' : '새 사용자를 생성합니다.'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700">이메일</label>
                <Input value={formEmail} onChange={(e) => setFormEmail(e.target.value)} placeholder="user@example.com" />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700">비밀번호 {editingUser ? '(선택)' : ''}</label>
                <Input value={formPassword} onChange={(e) => setFormPassword(e.target.value)} placeholder="******" type="password" />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700">역할</label>
                <Select value={formRole} onValueChange={(v: any) => setFormRole(v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="역할 선택" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">admin</SelectItem>
                    <SelectItem value="researcher">researcher</SelectItem>
                    <SelectItem value="subject">subject</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {editingUser && (
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-700">활성 상태</p>
                    <p className="text-xs text-gray-500">비활성 사용자는 로그인할 수 없습니다.</p>
                  </div>
                  <Switch checked={formActive} onCheckedChange={setFormActive} />
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>취소</Button>
              <Button className="bg-[#2563EB]" onClick={submitForm}>{editingUser ? '저장' : '생성'}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

function setSearchTermSafe(setter: (v: string) => void, value: string) {
  setter(value);
}
