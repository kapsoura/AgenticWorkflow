import { Brain, Cpu, Network, CheckCircle2, XCircle, Loader2, SkipForward, Circle } from 'lucide-react';
import type { StepEvent } from '../api/client';
import styles from './PipelineFlow.module.css';

const PIPELINE_STEPS = [
  { id: 'extraction', label: 'LLM Extraction', icon: Brain, description: 'AI extracts structured fields from the narrative' },
  { id: 'embedding', label: 'BGE Embedding', icon: Cpu, description: 'Generate a semantic vector for the complaint' },
  { id: 'cluster_assignment', label: 'Cluster Analysis', icon: Network, description: 'Find similar events & assign a signal cluster' },
] as const;

type StepStatus = 'idle' | 'processing' | 'success' | 'error' | 'skipped';

function StatusIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case 'success':
      return <CheckCircle2 size={16} className={`${styles.statusIcon} ${styles.success}`} />;
    case 'error':
      return <XCircle size={16} className={`${styles.statusIcon} ${styles.error}`} />;
    case 'processing':
      return <Loader2 size={16} className={`${styles.statusIcon} ${styles.processing} ${styles.spin}`} />;
    case 'skipped':
      return <SkipForward size={16} className={`${styles.statusIcon} ${styles.skipped}`} />;
    default:
      return <Circle size={16} className={styles.statusIcon} />;
  }
}

export interface PipelineFlowProps {
  steps: Record<string, StepEvent>;
  active: boolean;
  totalMs?: number;
}

export default function PipelineFlow({ steps, active, totalMs }: PipelineFlowProps) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <Network size={18} className={styles.cardIcon} />
        <h3>Processing Pipeline</h3>
        {totalMs !== undefined && <span className={styles.totalTime}>{totalMs} ms total</span>}
        {active && totalMs === undefined && <span className={styles.liveDot}>live</span>}
      </div>

      <div className={styles.steps}>
        {PIPELINE_STEPS.map((step, index) => {
          const ev = steps[step.id];
          const status: StepStatus = (ev?.status as StepStatus) ?? 'idle';
          const StepIcon = step.icon;
          const connectorActive = status === 'success' || status === 'skipped';
          return (
            <div key={step.id}>
              <div className={`${styles.step} ${styles[status]}`}>
                <div className={styles.stepIconWrap}>
                  <StepIcon size={20} />
                </div>
                <div className={styles.stepInfo}>
                  <div className={styles.stepTop}>
                    <span className={styles.stepLabel}>{step.label}</span>
                    <StatusIcon status={status} />
                  </div>
                  <span className={styles.stepDesc}>{step.description}</span>
                  {ev?.duration_ms !== undefined && status !== 'skipped' && (
                    <span className={styles.stepDuration}>{ev.duration_ms} ms</span>
                  )}
                  {status === 'skipped' && <span className={styles.stepDuration}>skipped</span>}
                </div>
              </div>
              {index < PIPELINE_STEPS.length - 1 && (
                <div className={`${styles.connector} ${connectorActive ? styles.connectorActive : ''}`}>
                  <div className={styles.connectorLine} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
