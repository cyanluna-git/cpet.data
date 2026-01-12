import { Activity, Users, LineChart, BarChart3, LogOut, User, Flame } from 'lucide-react';
import { Button } from './ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

interface NavigationProps {
  user: {
    name: string;
    email: string;
    role: string;
  };
  currentView: string;
  onNavigate: (view: any) => void;
  onLogout: () => void;
}

export function Navigation({ user, currentView, onNavigate, onLogout }: NavigationProps) {
  const isResearcher = user.role === 'researcher' || user.role === 'admin';

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => onNavigate(isResearcher ? 'researcher-dashboard' : 'subject-dashboard')}>
            <div className="w-10 h-10 bg-[#2563EB] rounded-lg flex items-center justify-center">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">CPET Platform</h1>
              <p className="text-xs text-gray-500">대사 분석 시스템</p>
            </div>
          </div>

          {/* Navigation Menu */}
          <div className="flex items-center gap-1">
            {isResearcher && (
              <>
                <Button
                  variant={currentView === 'researcher-dashboard' ? 'default' : 'ghost'}
                  onClick={() => onNavigate('researcher-dashboard')}
                  className="gap-2"
                >
                  <LineChart className="w-4 h-4" />
                  <span>대시보드</span>
                </Button>
                
                <Button
                  variant={currentView === 'subject-list' ? 'default' : 'ghost'}
                  onClick={() => onNavigate('subject-list')}
                  className="gap-2"
                >
                  <Users className="w-4 h-4" />
                  <span>피험자 관리</span>
                </Button>
                
                <Button
                  variant={currentView === 'cohort-analysis' ? 'default' : 'ghost'}
                  onClick={() => onNavigate('cohort-analysis')}
                  className="gap-2"
                >
                  <BarChart3 className="w-4 h-4" />
                  <span>코호트 분석</span>
                </Button>
                
                <Button
                  variant={currentView === 'metabolism' ? 'default' : 'ghost'}
                  onClick={() => onNavigate('metabolism')}
                  className="gap-2"
                >
                  <Flame className="w-4 h-4" />
                  <span>메타볼리즘</span>
                </Button>
              </>
            )}
            
            {!isResearcher && (
              <>
                <Button
                  variant={currentView === 'subject-dashboard' ? 'default' : 'ghost'}
                  onClick={() => onNavigate('subject-dashboard')}
                  className="gap-2"
                >
                  <LineChart className="w-4 h-4" />
                  <span>내 대시보드</span>
                </Button>
                
                <Button
                  variant={currentView === 'metabolism' ? 'default' : 'ghost'}
                  onClick={() => onNavigate('metabolism')}
                  className="gap-2"
                >
                  <Flame className="w-4 h-4" />
                  <span>메타볼리즘</span>
                </Button>
              </>
            )}

            {/* User Profile Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="ml-4 gap-2">
                  <div className="w-8 h-8 bg-[#2563EB] rounded-full flex items-center justify-center">
                    <User className="w-4 h-4 text-white" />
                  </div>
                  <span className="max-w-32 truncate">{user.name}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <div>
                    <p className="font-semibold">{user.name}</p>
                    <p className="text-xs text-gray-500">{user.email}</p>
                    <p className="text-xs text-[#2563EB] mt-1 capitalize">{user.role}</p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onLogout} className="text-red-600 cursor-pointer">
                  <LogOut className="w-4 h-4 mr-2" />
                  <span>로그아웃</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </nav>
  );
}