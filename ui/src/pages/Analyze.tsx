import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Send, AlertTriangle, CheckCircle, FileText } from 'lucide-react';
import { analyzeComplaint, fetchMeta } from '../api/client';
import type { AnalyzeResponse } from '../api/client';
import Spinner from '../components/Spinner';
import styles from './Analyze.module.css';

const SAMPLE_NARRATIVES = [
  {
    label: 'MRI Image Artifact',
    narrative:
      'During routine brain MRI scan, the system displayed persistent banding artifacts across all acquired sequences. The artifacts appeared as horizontal lines across the image, making diagnosis impossible. The technologist rebooted the system but the issue persisted. Service engineer was called.',
    product_code: 'LNH',
    event_type: 'Malfunction',
    manufacturer: 'Siemens Healthineers',
  },
  {
    label: 'CT Radiation Overdose',
    narrative:
      'Patient received approximately 3x the intended radiation dose during a CT chest exam. The system failed to terminate the scan at the programmed mAs limit. The patient was monitored and no immediate adverse effects were observed, but long-term follow-up was recommended.',
    product_code: 'JAK',
    event_type: 'Injury',
    manufacturer: 'GE Healthcare',
  },
  {
    label: 'Ultrasound Probe Failure',
    narrative:
      'The ultrasound transducer probe (C5-2) showed intermittent loss of signal during obstetric examination. Image quality degraded to the point where fetal heartbeat could not be reliably detected. Probe was replaced with backup and exam completed successfully.',
    product_code: 'LLZ',
    event_type: 'Malfunction',
    manufacturer: 'Philips Healthcare',
  },
];

export default function Analyze() {
  const [narrative, setNarrative] = useState('');
  const [productCode, setProductCode] = useState('LNH');
  const [eventType, setEventType] = useState('Malfunction');
  const [manufacturer, setManufacturer] = useState('');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: fetchMeta,
  });

  const analyzeMutation = useMutation({
    mutationFn: analyzeComplaint,
    onSuccess: (data) => setResult(data),
  });

  const handleAnalyze = () => {
    if (!narrative.trim()) return;
    analyzeMutation.mutate({
      narrative,
      product_code: productCode,
      event_type: eventType,
      manufacturer: manufacturer || 'Unknown',
    });
  };

  const loadSample = (idx: number) => {
    const s = SAMPLE_NARRATIVES[idx];
    setNarrative(s.narrative);
    setProductCode(s.product_code);
    setEventType(s.event_type);
    setManufacturer(s.manufacturer);
    setResult(null);
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Analyze Complaint</h1>
        <p className={styles.subtitle}>
          Submit an adverse event narrative for multi-agent analysis
        </p>
      </div>

      <div className={styles.grid}>
        {/* Input Panel */}
        <div className={styles.inputPanel}>
          <div className={styles.samples}>
            <span className={styles.samplesLabel}>Load sample:</span>
            {SAMPLE_NARRATIVES.map((s, i) => (
              <button
                key={i}
                className={styles.sampleBtn}
                onClick={() => loadSample(i)}
              >
                {s.label}
              </button>
            ))}
          </div>

          <label className={styles.label}>
            Complaint Narrative
            <textarea
              className={styles.textarea}
              placeholder="Enter the adverse event description..."
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              rows={8}
            />
          </label>

          <div className={styles.row}>
            <label className={styles.label}>
              Product Code
              <select
                className={styles.select}
                value={productCode}
                onChange={(e) => setProductCode(e.target.value)}
              >
                {(meta?.product_codes || ['LNH', 'JAK', 'LLZ']).map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.label}>
              Event Type
              <select
                className={styles.select}
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
              >
                {(meta?.event_types || ['Malfunction', 'Injury', 'Death']).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.label}>
              Manufacturer
              <input
                className={styles.input}
                type="text"
                placeholder="e.g. Siemens"
                value={manufacturer}
                onChange={(e) => setManufacturer(e.target.value)}
              />
            </label>
          </div>

          <div className={styles.actions}>
            <button
              className={styles.primaryBtn}
              onClick={handleAnalyze}
              disabled={!narrative.trim() || analyzeMutation.isPending}
            >
              {analyzeMutation.isPending ? (
                <Spinner size={16} />
              ) : (
                <Send size={16} />
              )}
              Analyze
            </button>
          </div>

          {analyzeMutation.isError && (
            <div className={styles.error}>
              <AlertTriangle size={16} />
              {analyzeMutation.error.message}
            </div>
          )}
        </div>

        {/* Results Panel */}
        <div className={styles.resultPanel}>
          {!result && !analyzeMutation.isPending && (
            <div className={styles.placeholder}>
              <FileText size={48} strokeWidth={1} />
              <p>Analysis results will appear here</p>
            </div>
          )}

          {analyzeMutation.isPending && (
            <div className={styles.placeholder}>
              <Spinner size={40} />
              <p>Running multi-agent pipeline...</p>
              <p className={styles.hint}>
                Extraction → Retrieval → Risk → Report
              </p>
            </div>
          )}

          {result && (
            <div className={styles.results}>
              <div className={styles.resultHeader}>
                <h3>Analysis Results</h3>
                <span className={styles.reportId}>{result.report_id}</span>
              </div>

              <div className={styles.badges}>
                {result.report_type && (
                  <span className={styles.badgeType}>{result.report_type}</span>
                )}
                {result.risk_bucket && (
                  <span
                    className={
                      result.risk_bucket === 'UNACCEPTABLE'
                        ? styles.badgeBad
                        : result.risk_bucket === 'ALARP'
                        ? styles.badgeWarn
                        : styles.badgeOk
                    }
                  >
                    {result.risk_bucket}
                  </span>
                )}
                {result.validation?.passed && (
                  <span className={styles.badgeOk}>
                    <CheckCircle size={12} /> Validated
                  </span>
                )}
              </div>

              {result.extraction && (
                <details className={styles.details}>
                  <summary>Extraction Output</summary>
                  <pre className={styles.pre}>
                    {JSON.stringify(result.extraction, null, 2)}
                  </pre>
                </details>
              )}

              {result.evidence_count !== undefined && (
                <div className={styles.infoRow}>
                  <span>Evidence Retrieved:</span>
                  <strong>{result.evidence_count} items</strong>
                </div>
              )}

              {result.sections && result.sections.length > 0 && (
                <div className={styles.sections}>
                  <h4>Report Sections</h4>
                  {result.sections.map((sec, i) => (
                    <details key={i} className={styles.details}>
                      <summary>{sec.title || sec.name}</summary>
                      <div className={styles.sectionContent}>{sec.content}</div>
                    </details>
                  ))}
                </div>
              )}

              {result.cluster && (
                <details className={styles.details}>
                  <summary>Cluster Assignment</summary>
                  <pre className={styles.pre}>
                    {JSON.stringify(result.cluster, null, 2)}
                  </pre>
                </details>
              )}

              {result.total_duration_ms !== undefined && (
                <div className={styles.infoRow}>
                  <span>Total Duration:</span>
                  <strong>{result.total_duration_ms} ms</strong>
                </div>
              )}

              {result.validation && !result.validation.passed && (
                <div className={styles.validationIssues}>
                  <h4>
                    <AlertTriangle size={14} /> Validation Issues
                  </h4>
                  <ul>
                    {result.validation.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
