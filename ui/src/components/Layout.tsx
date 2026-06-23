import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  FileSearch,
  TrendingUp,
  FileText,
  Play,
  Activity,
  Shield,
  Workflow as WorkflowIcon,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/client';
import { AnalysisProvider } from '../context/AnalysisContext';
import styles from './Layout.module.css';

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Overview' },
  { to: '/analyze', icon: FileSearch, label: 'Complaint Analysis' },
  { to: '/trends', icon: TrendingUp, label: 'Signal Trends' },
  { to: '/reports', icon: FileText, label: 'Report Templates' },
  { to: '/workflow', icon: Play, label: 'Live Pipeline' },
  { to: '/langgraph', icon: WorkflowIcon, label: 'LangGraph Flow' },
];

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 5_000,
    retry: 0,
  });

  const isOnline = health?.status === 'ok';

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <div className={styles.logo}>
            <Shield size={18} />
          </div>
          <div>
            <div className={styles.title}>Multi-Agent Quality Intelligence System</div>
            <div className={styles.subtitle}>FDA MAUDE Signal Pipeline</div>
          </div>
        </div>

        <nav className={styles.nav}>
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `${styles.navItem} ${isActive ? styles.active : ''}`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.status}>
          <Activity size={14} />
          <span className={isOnline ? styles.online : styles.offline}>
            {isOnline ? 'API Online' : 'API Offline'}
          </span>
        </div>
      </aside>

      <main className={styles.main}>
        <AnalysisProvider>
          <Outlet />
        </AnalysisProvider>
      </main>
    </div>
  );
}
