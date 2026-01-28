import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity } from 'lucide-react';

interface LoginPageProps {
  onLogin: (email: string, password: string) => Promise<void>;
  onDemoLogin?: (role: 'researcher' | 'subject') => void;
}

// 개발 모드 체크 (Vite)
const isDev = import.meta.env.DEV;

export function LoginPage({ onLogin, onDemoLogin }: LoginPageProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    
    try {
      await onLogin(email, password);
    } catch (error) {
      console.error('Login error:', error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-gray-50 p-4">
      <Card className="w-full max-w-md shadow-xl">
        <CardHeader className="space-y-4 text-center pb-8">
          <div className="flex justify-center">
            <div className="w-16 h-16 bg-[#2563EB] rounded-full flex items-center justify-center">
              <Activity className="w-9 h-9 text-white" />
            </div>
          </div>
          <div>
            <CardTitle className="text-3xl font-bold text-gray-900">CPET 분석 플랫폼</CardTitle>
            <CardDescription className="text-base mt-2">
              대사 프로파일 분석 및 시각화 시스템
            </CardDescription>
          </div>
        </CardHeader>
        
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-semibold text-gray-700">
                이메일
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-12 border-gray-300 focus:border-[#2563EB] focus:ring-[#2563EB]"
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-semibold text-gray-700">
                비밀번호
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-12 border-gray-300 focus:border-[#2563EB] focus:ring-[#2563EB]"
              />
            </div>

            <div className="flex items-center justify-between text-sm">
              <a href="#" className="text-[#2563EB] hover:underline font-medium">
                비밀번호 찾기
              </a>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-12 bg-[#2563EB] hover:bg-[#1d4ed8] text-white font-semibold text-base transition-colors"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>로그인 중...</span>
                </div>
              ) : (
                '로그인'
              )}
            </Button>
          </form>

          {/* Demo Login Buttons - 개발 모드에서만 표시 */}
          {isDev && onDemoLogin && (
            <div className="mt-6 pt-6 border-t">
              <p className="text-sm text-gray-500 text-center mb-3">개발 모드 - 데모 로그인</p>
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => onDemoLogin('researcher')}
                >
                  연구자 데모
                </Button>
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => onDemoLogin('subject')}
                >
                  피험자 데모
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}