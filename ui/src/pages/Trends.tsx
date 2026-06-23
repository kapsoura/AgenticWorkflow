import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { fetchTrends, fetchMeta } from '../api/client';
import Spinner from '../components/Spinner';
import styles from './Trends.module.css';

const DIMENSIONS = [
  { value: 'product_code', label: 'Product Code' },
  { value: 'event_type', label: 'Event Type' },
  { value: 'manufacturer', label: 'Manufacturer' },
  { value: 'product_problem', label: 'Product Problem' },
  { value: 'year', label: 'Year' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'risk_bucket', label: 'Risk Bucket' },
  { value: 'report_type', label: 'Report Type' },
];

const TIME_DIMENSIONS = new Set(['year', 'month', 'quarter', 'report_year', 'report_month']);

export default function Trends() {
  const [dimension, setDimension] = useState('product_code');
  const [productCode, setProductCode] = useState('');
  const [eventType, setEventType] = useState('');

  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: fetchMeta,
  });

  const filters = {
    ...(productCode ? { product_code: productCode } : {}),
    ...(eventType ? { event_type: eventType } : {}),
  };

  const { data: trends, isLoading } = useQuery({
    queryKey: ['trends', dimension, filters],
    queryFn: () => fetchTrends(dimension, filters),
  });

  const chartData = trends?.series?.map((s) => ({
    name: s.label,
    count: s.count,
  })) || [];

  const isTimeSeries = TIME_DIMENSIONS.has(dimension);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Trends & Analytics</h1>
        <p className={styles.subtitle}>
          Explore adverse event distributions and temporal trends
        </p>
      </div>

      <div className={styles.controls}>
        <label className={styles.control}>
          <span>Dimension</span>
          <select
            value={dimension}
            onChange={(e) => setDimension(e.target.value)}
          >
            {DIMENSIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.control}>
          <span>Product Code</span>
          <select
            value={productCode}
            onChange={(e) => setProductCode(e.target.value)}
          >
            <option value="">All</option>
            {meta?.product_codes?.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.control}>
          <span>Event Type</span>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
          >
            <option value="">All</option>
            {meta?.event_types?.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className={styles.chartPanel}>
        {isLoading ? (
          <div className={styles.loading}>
            <Spinner size={32} />
          </div>
        ) : chartData.length === 0 ? (
          <div className={styles.empty}>No data for this combination</div>
        ) : isTimeSeries ? (
          <ResponsiveContainer width="100%" height={380}>
            <LineChart data={chartData} margin={{ top: 10, right: 30, bottom: 30, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="name"
                stroke="#64748b"
                fontSize={11}
                angle={-35}
                textAnchor="end"
                height={60}
              />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                labelStyle={{ color: '#1e293b', fontWeight: 600 }}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#2563eb"
                strokeWidth={2.5}
                dot={{ fill: '#2563eb', r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={chartData} margin={{ top: 10, right: 30, bottom: 60, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="name"
                stroke="#64748b"
                fontSize={11}
                angle={-35}
                textAnchor="end"
                height={80}
              />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                labelStyle={{ color: '#1e293b', fontWeight: 600 }}
              />
              <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {chartData.length > 0 && (
        <div className={styles.table}>
          <table>
            <thead>
              <tr>
                <th>{dimension.replace(/_/g, ' ')}</th>
                <th>Count</th>
                <th>% of Total</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((row, i) => {
                const total = chartData.reduce((s, r) => s + r.count, 0);
                const pct = total > 0 ? ((row.count / total) * 100).toFixed(1) : '0';
                return (
                  <tr key={i}>
                    <td>{row.name}</td>
                    <td>{row.count.toLocaleString()}</td>
                    <td>{pct}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
