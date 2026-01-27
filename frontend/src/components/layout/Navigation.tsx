import { useState } from 'react';
import { Activity, Users, LineChart, BarChart3, LogOut, User, Flame, Shield, Database, Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetClose,
} from '@/components/ui/sheet';
import { useIsMobile } from '@/components/ui/use-mobile';

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
  const isAdmin = user.role === 'admin';
  const isMobile = useIsMobile();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleNavigate = (view: any) => {
    onNavigate(view);
    setMobileMenuOpen(false);
  };

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 md:px-6">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div
            className="flex items-center gap-3 cursor-pointer"
            onClick={() => onNavigate(isAdmin ? 'admin-dashboard' : (isResearcher ? 'researcher-dashboard' : 'subject-dashboard'))}
          >
            <div className="w-10 h-10 bg-[#2563EB] rounded-lg flex items-center justify-center">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">CPET Platform</h1>
              <p className="text-xs text-gray-500">대사 분석 시스템</p>
            </div>
          </div>

          {/* Desktop Navigation Menu */}
          <div className="hidden md:flex items-center gap-1">
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
              </>
            )}

            {/* 코호트 분석 - 연구자/어드민만 */}
            {isResearcher && (
              <Button
                variant={currentView === 'cohort-analysis' ? 'default' : 'ghost'}
                onClick={() => onNavigate('cohort-analysis')}
                className="gap-2"
              >
                <BarChart3 className="w-4 h-4" />
                <span>코호트 분석</span>
              </Button>
            )}

            <Button
              variant={currentView === 'metabolism' ? 'default' : 'ghost'}
              onClick={() => onNavigate('metabolism')}
              className="gap-2"
            >
              <Flame className="w-4 h-4" />
              <span>메타볼리즘</span>
            </Button>

            {/* Raw Data - Admin/Researcher only */}
            {isResearcher && (
              <Button
                variant={currentView === 'raw-data' ? 'default' : 'ghost'}
                onClick={() => onNavigate('raw-data')}
                className="gap-2"
              >
                <Database className="w-4 h-4" />
                <span>Raw Data</span>
              </Button>
            )}

            {/* Super Admin - Admin/Researcher only */}
            {isResearcher && (
              <Button
                variant={currentView === 'admin-dashboard' || currentView?.startsWith('admin-') ? 'default' : 'ghost'}
                onClick={() => onNavigate('admin-dashboard')}
                className="gap-2"
              >
                <Shield className="w-4 h-4" />
                <span>슈퍼어드민</span>
              </Button>
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

          {/* Mobile Navigation */}
          <div className="flex md:hidden items-center gap-2">
            <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
              <Button
                variant="ghost"
                size="icon"
                className="h-10 w-10"
                onClick={() => setMobileMenuOpen(true)}
              >
                <Menu className="h-5 w-5" />
                <span className="sr-only">메뉴 열기</span>
              </Button>
              <SheetContent side="left" className="w-72 p-0">
                <SheetHeader className="border-b p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-[#2563EB] rounded-lg flex items-center justify-center">
                      <Activity className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <SheetTitle className="text-left">CPET Platform</SheetTitle>
                      <p className="text-xs text-gray-500">대사 분석 시스템</p>
                    </div>
                  </div>
                </SheetHeader>

                <nav className="flex flex-col p-2">
                  {isResearcher && (
                    <>
                      <SheetClose asChild>
                        <Button
                          variant={currentView === 'researcher-dashboard' ? 'secondary' : 'ghost'}
                          onClick={() => handleNavigate('researcher-dashboard')}
                          className="justify-start gap-3 h-11"
                        >
                          <LineChart className="w-5 h-5" />
                          <span>대시보드</span>
                        </Button>
                      </SheetClose>

                      <SheetClose asChild>
                        <Button
                          variant={currentView === 'subject-list' ? 'secondary' : 'ghost'}
                          onClick={() => handleNavigate('subject-list')}
                          className="justify-start gap-3 h-11"
                        >
                          <Users className="w-5 h-5" />
                          <span>피험자 관리</span>
                        </Button>
                      </SheetClose>
                    </>
                  )}

                  {!isResearcher && (
                    <SheetClose asChild>
                      <Button
                        variant={currentView === 'subject-dashboard' ? 'secondary' : 'ghost'}
                        onClick={() => handleNavigate('subject-dashboard')}
                        className="justify-start gap-3 h-11"
                      >
                        <LineChart className="w-5 h-5" />
                        <span>내 대시보드</span>
                      </Button>
                    </SheetClose>
                  )}

                  {isResearcher && (
                    <SheetClose asChild>
                      <Button
                        variant={currentView === 'cohort-analysis' ? 'secondary' : 'ghost'}
                        onClick={() => handleNavigate('cohort-analysis')}
                        className="justify-start gap-3 h-11"
                      >
                        <BarChart3 className="w-5 h-5" />
                        <span>코호트 분석</span>
                      </Button>
                    </SheetClose>
                  )}

                  <SheetClose asChild>
                    <Button
                      variant={currentView === 'metabolism' ? 'secondary' : 'ghost'}
                      onClick={() => handleNavigate('metabolism')}
                      className="justify-start gap-3 h-11"
                    >
                      <Flame className="w-5 h-5" />
                      <span>메타볼리즘</span>
                    </Button>
                  </SheetClose>

                  {isResearcher && (
                    <>
                      <SheetClose asChild>
                        <Button
                          variant={currentView === 'raw-data' ? 'secondary' : 'ghost'}
                          onClick={() => handleNavigate('raw-data')}
                          className="justify-start gap-3 h-11"
                        >
                          <Database className="w-5 h-5" />
                          <span>Raw Data</span>
                        </Button>
                      </SheetClose>

                      <SheetClose asChild>
                        <Button
                          variant={currentView === 'admin-dashboard' || currentView?.startsWith('admin-') ? 'secondary' : 'ghost'}
                          onClick={() => handleNavigate('admin-dashboard')}
                          className="justify-start gap-3 h-11"
                        >
                          <Shield className="w-5 h-5" />
                          <span>슈퍼어드민</span>
                        </Button>
                      </SheetClose>
                    </>
                  )}
                </nav>

                {/* User section at bottom */}
                <div className="mt-auto border-t p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 bg-[#2563EB] rounded-full flex items-center justify-center">
                      <User className="w-5 h-5 text-white" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-900 truncate">{user.name}</p>
                      <p className="text-xs text-gray-500 truncate">{user.email}</p>
                      <p className="text-xs text-[#2563EB] capitalize">{user.role}</p>
                    </div>
                  </div>
                  <SheetClose asChild>
                    <Button
                      variant="outline"
                      className="w-full justify-start gap-2 h-11 text-red-600 hover:text-red-700 hover:bg-red-50"
                      onClick={onLogout}
                    >
                      <LogOut className="w-4 h-4" />
                      로그아웃
                    </Button>
                  </SheetClose>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </div>
    </nav>
  );
}