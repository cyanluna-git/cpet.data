import { useState, useEffect, createContext, useContext, type ReactNode } from 'react';
import { api } from '@/lib/api';

export interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'researcher' | 'subject';
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  demoMode: boolean;
  login: (email: string, password: string) => Promise<void>;
  demoLogin: (role: 'researcher' | 'subject') => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      // 데모 모드 체크
      if (localStorage.getItem('demoMode') === 'true') {
        setDemoMode(true);
        const userData = await api.getCurrentUser();
        setUser(userData as User);
      } else {
        const session = await api.getSession();
        if (session) {
          const userData = await api.getCurrentUser();
          setUser(userData as User);
        }
      }
    } catch (error) {
      console.log('Not authenticated');
    } finally {
      setLoading(false);
    }
  }

  async function login(email: string, password: string) {
    await api.signIn(email, password);
    const userData = await api.getCurrentUser();
    setUser(userData as User);
    setDemoMode(false);
  }

  function demoLogin(role: 'researcher' | 'subject') {
    const demoUsers = {
      researcher: {
        id: 'demo-researcher-1',
        email: 'demo@researcher.com',
        name: '연구자 데모',
        role: 'researcher' as const,
      },
      subject: {
        id: '660e8400-e29b-41d4-a716-446655440001',
        email: 'demo@subject.com',
        name: '박용두',
        role: 'subject' as const,
      }
    };

    const demoUser = demoUsers[role];
    setUser(demoUser);
    setDemoMode(true);
    localStorage.setItem('demoMode', 'true');
    localStorage.setItem('demoRole', role);
  }

  async function logout() {
    await api.signOut();
    setUser(null);
    setDemoMode(false);
    localStorage.removeItem('demoMode');
    localStorage.removeItem('demoRole');
  }

  return (
    <AuthContext.Provider value={{ user, loading, demoMode, login, demoLogin, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
