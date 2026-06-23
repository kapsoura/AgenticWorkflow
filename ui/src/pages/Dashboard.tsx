import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer, Legend,
} from 'recharts';
import { fetchStats, fetchTrends, fetchMeta } from '../api/client';
import { StatCard } from '../components/Card';
import Spinner from '../components/Spinner';
import styles from './Dashboard.module.css';

const COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#059669', '#f59e0b', '#ec4899'];

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
  });

  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: fetchMeta,
  });

  const { data: productTrend } = useQuery({
    queryKey: ['trends', 'product_code'],
    queryFn: () => fetchTrends('product_code'),
  });

  const { data: eventTypeTrend } = useQuery({
    queryKey: ['trends', 'event_type'],
    queryFn: () => fetchTrends('event_type'),
  });

  if (statsLoading) {
    return (
      <div className={styles.loading}>
        <Spinner size={40} />
        <p>Loading dashboard...</p>
      </div>
    );
  }

  const eventTypeData = eventTypeTrend?.series?.map((s) => ({
    name: s.label,
    value: s.count,
  })) || [];

  const productData = productTrend?.series?.map((s) => ({
    name: s.label,
    count: s.count,
  })) || [];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Regulatory Signal Intelligence</h1>
        <p className={styles.subtitle}>
          FDA Adverse Event Monitoring & Medical Device Compliance Dashboard
        </p>
      </div>

      <div className={styles.statsGrid}>
        <StatCard
          label="Total Events"
          value={stats?.total_events?.toLocaleString() ?? '—'}
        />
        <StatCard
          label="With Narrative"
          value={stats?.events_with_narrative?.toLocaleString() ?? '—'}
        />
        <StatCard
          label="Extracted"
          value={stats?.extracted_events?.toLocaleString() ?? '—'}
        />
        <StatCard
          label="Total Recalls"
          value={stats?.total_recalls?.toLocaleString() ?? '—'}
        />
        <StatCard
          label="Clusters"
          value={stats?.total_clusters?.toLocaleString() ?? '—'}
        />
      </div>

      <div className={styles.chartsGrid}>
        <div className={styles.chartCard}>
          <h3>Events by Product Code</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={productData} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                labelStyle={{ color: '#1e293b', fontWeight: 600 }}
              />
              <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className={styles.chartCard}>
          <h3>Events by Type</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={eventTypeData}
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={90}
                dataKey="value"
                labelLine={false}
              >
                {eventTypeData.map((_, idx) => (
                  <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                formatter={(value, name) => [`${Number(value ?? 0).toLocaleString()} events`, name]}
              />
              <Legend
                layout="vertical"
                align="right"
                verticalAlign="middle"
                iconSize={10}
                wrapperStyle={{ fontSize: '0.78rem', color: '#94a3b8' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {meta && (
        <div className={styles.metaCard}>
          <h3>System Configuration</h3>
          <div className={styles.metaGrid}>
            <div>
              <span className={styles.metaLabel}>Product Codes</span>
              <div className={styles.tags}>
                {meta.product_codes.map((code) => (
                  <span key={code} className={styles.tag}>{code}</span>
                ))}
              </div>
            </div>
            <div>
              <span className={styles.metaLabel}>Event Types</span>
              <div className={styles.tags}>
                {meta.event_types.map((t) => (
                  <span key={t} className={styles.tag}>{t}</span>
                ))}
              </div>
            </div>
            <div>
              <span className={styles.metaLabel}>Report Types</span>
              <div className={styles.tags}>
                {meta.report_types.map((r) => (
                  <span key={r} className={styles.tagAccent}>{r}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
