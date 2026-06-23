import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Play, CheckCircle, AlertTriangle, Settings } from 'lucide-react';
import { processComplaint } from '../api/client';
import Spinner from '../components/Spinner';
import styles from './Workflow.module.css';

export default function Workflow() {
  const [narrative, setNarrative] = useState('');
  const [reportId, setReportId] = useState('PIPE-001');
  const [skipExtraction, setSkipExtraction] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const mutation = useMutation({
    mutationFn: processComplaint,
    onSuccess: (data) => setResult(data),
  });

  const handleRun = () => {
    if (!narrative.trim()) return;
    setResult(null);
    mutation.mutate({
      narrative,
      report_id: reportId,
      skip_extraction: skipExtraction,
    });
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Process Complaint</h1>
        <p className={styles.subtitle}>
          Run a complaint through the full pipeline: Extraction → Embedding → Cluster Assignment
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
            disabled={!narrative.trim() || mutation.isPending}
          >
            {mutation.isPending ? <Spinner size={18} /> : <Play size={18} />}
            {mutation.isPending ? 'Processing...' : 'Run Pipeline'}
          </button>

          {mutation.isPending && (
            <div className={styles.progressNote}>
              <Spinner size={14} />
              <span>Processing complaint through pipeline steps...</span>
            </div>
          )}
        </div>

        <div className={styles.resultPanel}>
          {!result && !mutation.isPending && !mutation.isError && (
            <div className={styles.placeholder}>
              <Play size={48} strokeWidth={1} />
              <p>Configure and run the workflow</p>
              <p className={styles.hintText}>
                The pipeline processes complaints through all 4 agents
              </p>
            </div>
          )}

          {mutation.isError && (
            <div className={styles.errorPanel}>
              <AlertTriangle size={20} />
              <h4>Workflow Failed</h4>
              <p>{mutation.error.message}</p>
            </div>
          )}

          {result && (
            <div className={styles.resultContent}>
              <div className={styles.successHeader}>
                <CheckCircle size={20} />
                <h3>Workflow Complete</h3>
              </div>

              <pre className={styles.resultJson}>
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
