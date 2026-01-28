import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Navigation } from '@/components/layout/Navigation';

// Mock useIsMobile hook for consistent testing (always desktop view)
vi.mock('@/components/ui/use-mobile', () => ({
  useIsMobile: () => false,
}));

describe('Navigation', () => {
  const mockUser = {
    email: 'test@example.com',
    name: '테스트 유저',
    role: 'researcher' as const,
  };

  const mockOnLogout = vi.fn();
  const mockOnNavigate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the logo and title', () => {
    render(
      <Navigation
        user={mockUser}
        currentView="researcher-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    expect(screen.getByText('CPET Platform')).toBeInTheDocument();
    // 대사 분석 시스템은 모바일에서도 보이므로 getAllByText 사용
    const subtitles = screen.getAllByText('대사 분석 시스템');
    expect(subtitles.length).toBeGreaterThanOrEqual(1);
  });

  it('renders navigation buttons for researcher', () => {
    render(
      <Navigation
        user={mockUser}
        currentView="researcher-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    // Desktop navigation should be visible
    expect(screen.getByText('대시보드')).toBeInTheDocument();
    expect(screen.getByText('피험자 관리')).toBeInTheDocument();
    expect(screen.getByText('코호트 분석')).toBeInTheDocument();
    expect(screen.getByText('메타볼리즘')).toBeInTheDocument();
  });

  it('renders admin navigation for admin role', () => {
    const adminUser = { ...mockUser, role: 'admin' as const };

    render(
      <Navigation
        user={adminUser}
        currentView="admin-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    expect(screen.getByText('슈퍼어드민')).toBeInTheDocument();
    expect(screen.getByText('Raw Data')).toBeInTheDocument();
  });

  it('renders subject-specific navigation for subject role', () => {
    const subjectUser = { ...mockUser, role: 'subject' as const };

    render(
      <Navigation
        user={subjectUser}
        currentView="subject-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    expect(screen.getByText('내 대시보드')).toBeInTheDocument();
    expect(screen.getByText('메타볼리즘')).toBeInTheDocument();
    // Subject should not see researcher-only items
    expect(screen.queryByText('피험자 관리')).not.toBeInTheDocument();
    expect(screen.queryByText('코호트 분석')).not.toBeInTheDocument();
  });

  it('calls onNavigate when navigation button is clicked', () => {
    render(
      <Navigation
        user={mockUser}
        currentView="researcher-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    const metabolismButton = screen.getByText('메타볼리즘');
    fireEvent.click(metabolismButton);

    expect(mockOnNavigate).toHaveBeenCalledWith('metabolism');
  });

  it('calls onNavigate with different view names', () => {
    render(
      <Navigation
        user={mockUser}
        currentView="researcher-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    fireEvent.click(screen.getByText('피험자 관리'));
    expect(mockOnNavigate).toHaveBeenCalledWith('subject-list');

    fireEvent.click(screen.getByText('코호트 분석'));
    expect(mockOnNavigate).toHaveBeenCalledWith('cohort-analysis');
  });

  it('displays user name in navigation', () => {
    render(
      <Navigation
        user={mockUser}
        currentView="researcher-dashboard"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    // User name should be visible in the navigation
    expect(screen.getByText('테스트 유저')).toBeInTheDocument();
  });

  it('navigates to dashboard when logo is clicked', () => {
    render(
      <Navigation
        user={mockUser}
        currentView="metabolism"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    // Click on the logo area (CPET Platform text)
    fireEvent.click(screen.getByText('CPET Platform'));
    expect(mockOnNavigate).toHaveBeenCalledWith('researcher-dashboard');
  });

  it('navigates to subject dashboard for subject users when logo clicked', () => {
    const subjectUser = { ...mockUser, role: 'subject' as const };

    render(
      <Navigation
        user={subjectUser}
        currentView="metabolism"
        onNavigate={mockOnNavigate}
        onLogout={mockOnLogout}
      />
    );

    fireEvent.click(screen.getByText('CPET Platform'));
    expect(mockOnNavigate).toHaveBeenCalledWith('subject-dashboard');
  });
});
