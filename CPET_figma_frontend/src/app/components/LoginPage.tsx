import { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Activity, User, UserCog } from 'lucide-react';

interface LoginPageProps {
  onLogin: (email: string, password: string) => Promise<void>;
  onDemoLogin: (role: 'researcher' | 'subject') => void;
}

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

          <div className="mt-6 pt-6 border-t border-gray-200 space-y-4">
            <div className="text-center mb-3">
              <p className="text-sm font-semibold text-gray-700 mb-1">
                로그인 없이 데모로 체험하기
              </p>
              <p className="text-xs text-gray-500">
                실제 데이터로 모든 기능을 바로 테스트할 수 있습니다
              </p>
            </div>
            
            <div className="grid grid-cols-2 gap-3">
              <Button
                type="button"
                onClick={() => onDemoLogin('researcher')}
                variant="outline"
                className="h-11 border-[#2563EB] text-[#2563EB] hover:bg-[#2563EB] hover:text-white transition-colors"
              >
                <UserCog className="w-4 h-4 mr-2" />
                연구자 데모
              </Button>
              
              <Button
                type="button"
                onClick={() => onDemoLogin('subject')}
                variant="outline"
                className="h-11 border-[#2563EB] text-[#2563EB] hover:bg-[#2563EB] hover:text-white transition-colors"
              >
                <User className="w-4 h-4 mr-2" />
                피험자 데모
              </Button>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200">
            <p className="text-xs text-center text-gray-500">
              실제 로그인 계정이 필요하신 경우 관리자에게 문의하세요
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}