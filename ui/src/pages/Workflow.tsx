import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  Play,
  AlertTriangle,
  Settings,
  Layers,
  TrendingUp,
} from 'lucide-react';
import { streamProcess, fetchMeta } from '../api/client';
import type { StepEvent } from '../api/client';
import Spinner from '../components/Spinner';
import PipelineFlow from '../components/PipelineFlow';
import styles from './Workflow.module.css';

interface SimilarEvent {
  report_number: string;
  similarity_score: number;
  narrative_preview?: string;
  product_code?: string;
  manufacturer?: string;
}

interface ClusterData {
  cluster_id?: number;
  cluster_label?: string;
  trend_flag?: string;
  cluster_size?: number;
  growth_rate_30d?: number;
  similar_events?: SimilarEvent[];
}

interface TrendData {
  product_code?: string;
  series?: { label: string; count: number }[];
}

export default function Workflow() {
  const [narrative, setNarrative] = useState('');
  const [reportId, setReportId] = useState('PIPE-001');
  const [productCode, setProductCode] = useState('LNH');
  const [skipExtraction, setSkipExtraction] = useState(true);

  const [steps, setSteps] = useState<Record<string, StepEvent>>({});
  const [cluster, setCluster] = useState<ClusterData | null>(null);
  const [trend, setTrend] = useState<TrendData | null>(null);
  const [totalMs, setTotalMs] = useState<number | undefined>(undefined);
  const [running, setRunning] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: fetchMeta });

  const handleRun = async () => {
    if (!narrative.trim()) return;
    setSteps({});
    setCluster(null);
    setTrend(null);
    setTotalMs(undefined);
    setError(null);
    setStarted(true);
    setRunning(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamProcess(
        { narrative, report_id: reportId, skip_extraction: skipExtraction, product_code: productCode },
        (event, data) => {
          if (event === 'step') {
            const ev = data as unknown as StepEvent;
            setSteps((prev) => ({ ...prev, [ev.step]: ev }));
          } else if (event === 'cluster') {
            setCluster(data as ClusterData);
          } else if (event === 'trend') {
            setTrend(data as TrendData);
          } else if (event === 'done') {
            setTotalMs(data.total_duration_ms as number);
          }
        },
        controller.signal
      );
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError((e as Error).message);
      }
    } finally {
      setRunning(false);
    }
  };

  const trendFlagClass = (flag?: string) => {
    if (!flag) return styles.flagNeutral;
    const f = flag.toUpperCase();
    if (f.includes('SPIK') || f.includes('UP') || f.includes('EMERG')) return styles.flagBad;
    if (f.includes('STABLE') || f.includes('FLAT')) return styles.flagNeutral;
    return styles.flagWarn;
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Live Pipeline</h1>
        <p className={styles.subtitle}>
          Watch the agentic flow run live: Extraction → Embedding → Cluster Assignment
        </p>
      </div>

      <div className={styles.grid}>
        <div className={styles.configPanel}>
          <div className={styles.configHeader}>
            <Settings size={18} />
            <h3>Pipeline Configuration</h3>
          </div>

          <label className={styles.label}>
            Complaint Narrative
            <textarea
              className={styles.textarea}
              placeholder="Enter adverse event narrative..."
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              rows={6}
            />
          </label>

          <label className={styles.label}>
            Product Code
            <select
              className={styles.input}
              value={productCode}
              onChange={(e) => setProductCode(e.target.value)}
            >
              {(meta?.product_codes || ['LNH', 'JAK', 'LLZ']).map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
            <span className={styles.hint}>Used for the incoming-complaint trend</span>
          </label>

          <label className={styles.label}>
            Report ID
            <input
              className={styles.input}
              type="text"
              value={reportId}
              onChange={(e) => setReportId(e.target.value)}
            />
            <span className={styles.hint}>Identifier for this complaint</span>
          </label>

          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={skipExtraction}
              onChange={(e) => setSkipExtraction(e.target.checked)}
            />
            Skip LLM extraction (faster, embedding + clustering only)
          </label>

          <button
            className={styles.runBtn}
            onClick={handleRun}
            disabled={!narrative.trim() || running}
          >
            {running ? <Spinner size={18} /> : <Play size={18} />}
            {running ? 'Streaming...' : 'Run Pipeline'}
          </button>

          {running && (
            <div className={styles.progressNote}>
              <Spinner size={14} />
              <span>Streaming pipeline steps live...</span>
            </div>
          )}
        </div>

        <div className={styles.resultPanel}>
          {!started && (
            <div className={styles.placeholder}>
              <Play size={48} strokeWidth={1} />
              <p>Configure and run the workflow</p>
              <p className={styles.hintText}>
                The pipeline streams each step as it executes
              </p>
            </div>
          )}

          {error && (
            <div className={styles.errorPanel}>
              <AlertTriangle size={20} />
              <h4>Workflow Failed</h4>
              <p>{error}</p>
            </div>
          )}

          {started && !error && (
            <div className={styles.resultContent}>
              <PipelineFlow steps={steps} active={running} totalMs={totalMs} />

              {cluster && (
                <div className={styles.infoCard}>
                  <div className={styles.infoCardHeader}>
                    <Layers size={16} />
                    <h4>Cluster Membership</h4>
                    {cluster.trend_flag && (
                      <span className={`${styles.flag} ${trendFlagClass(cluster.trend_flag)}`}>
                        {cluster.trend_flag}
                      </span>
                    )}
                  </div>
                  <div className={styles.metaRow}>
                    <div>
                      <span className={styles.metaLabel}>Cluster</span>
                      <strong>
                        {cluster.cluster_label || 'Unlabeled'} (#{cluster.cluster_id})
                      </strong>
                    </div>
                    <div>
                      <span className={styles.metaLabel}>Size</span>
                      <strong>{cluster.cluster_size ?? '—'}</strong>
                    </div>
                    <div>
                      <span className={styles.metaLabel}>30d Growth</span>
                      <strong>
                        {cluster.growth_rate_30d !== undefined
                          ? `${cluster.growth_rate_30d.toFixed(1)}%`
                          : '—'}
                      </strong>
                    </div>
                  </div>
                  {cluster.similar_events && cluster.similar_events.length > 0 && (
                    <div className={styles.similarList}>
                      <span className={styles.metaLabel}>Similar events</span>
                      {cluster.similar_events.slice(0, 5).map((ev) => (
                        <div key={ev.report_number} className={styles.similarItem}>
                          <div className={styles.similarTop}>
                            <span className={styles.similarId}>{ev.report_number}</span>
                            <span className={styles.similarScore}>
                              {(ev.similarity_score * 100).toFixed(0)}%
                            </span>
                          </div>
                          {ev.narrative_preview && (
                            <p className={styles.similarText}>{ev.narrative_preview}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {trend && trend.series && trend.series.length > 0 && (
                <div className={styles.infoCard}>
                  <div className={styles.infoCardHeader}>
                    <TrendingUp size={16} />
                    <h4>Trend for {trend.product_code}</h4>
                  </div>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={trend.series} margin={{ top: 8, right: 8, bottom: 8, left: -16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--muted)" />
                      <YAxis tick={{ fontSize: 11 }} stroke="var(--muted)" allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {!running && (
                <div className={styles.downloadNote}>
                  Use the Analyze page to generate downloadable DOCX reports.
                </div>
              )}

              <details className={styles.details}>
                <summary>Raw step data</summary>
                <pre className={styles.resultJson}>
                  {JSON.stringify({ steps, cluster, trend }, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
