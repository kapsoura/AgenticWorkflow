import { useMutation, useQuery } from '@tanstack/react-query';
import { Send, AlertTriangle, CheckCircle, FileText, Download } from 'lucide-react';
import { analyzeComplaint, fetchMeta } from '../api/client';
import type { AnalyzeResponse } from '../api/client';
import { useAnalysis } from '../context/AnalysisContext';
import { buildReportMarkdown } from '../utils/report';
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
  const { inputs, setInputs, result, setResult } = useAnalysis();
  const { narrative, productCode, eventType, manufacturer } = inputs;

  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: fetchMeta,
  });

  const analyzeMutation = useMutation({
    mutationFn: analyzeComplaint,
    onSuccess: (data: AnalyzeResponse) => setResult(data),
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
    setInputs({
      narrative: s.narrative,
      productCode: s.product_code,
      eventType: s.event_type,
      manufacturer: s.manufacturer,
    });
    setResult(null);
  };

  const handleDownload = () => {
    if (!result) return;
    const markdown = buildReportMarkdown(result, inputs);
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.report_id || 'analysis'}.md`;
    a.click();
    URL.revokeObjectURL(url);
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
              onChange={(e) => setInputs({ ...inputs, narrative: e.target.value })}
              rows={8}
            />
          </label>

          <div className={styles.row}>
            <label className={styles.label}>
              Product Code
              <select
                className={styles.select}
                value={productCode}
                onChange={(e) => setInputs({ ...inputs, productCode: e.target.value })}
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
                onChange={(e) => setInputs({ ...inputs, eventType: e.target.value })}
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
                onChange={(e) => setInputs({ ...inputs, manufacturer: e.target.value })}
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
                <button className={styles.downloadBtn} onClick={handleDownload}>
                  <Download size={14} />
                  Download
                </button>
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

              {result.extraction_status && !result.extraction_status.ok && (
                <div className={styles.warnBanner}>
                  <AlertTriangle size={14} />
                  <span>{result.extraction_status.message}</span>
                </div>
              )}

              {result.risk && (
                <div className={styles.riskBlock}>
                  <h4>
                    Risk Analysis
                    <span className={styles.riskMethod}>
                      {result.risk.method === 'anthropic'
                        ? 'LLM (Anthropic)'
                        : result.risk.method === 'deterministic'
                        ? 'Deterministic ISO 14971'
                        : 'Unavailable'}
                    </span>
                  </h4>
                  <p className={styles.riskRationale}>{result.risk.rationale}</p>
                  {result.risk.signals.length > 0 && (
                    <ul className={styles.signalList}>
                      {result.risk.signals.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

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

              {result.cluster?.similar_events && result.cluster.similar_events.length > 0 && (
                <div className={styles.evidenceBlock}>
                  <h4>Retrieved Similar Events</h4>
                  {result.cluster.similar_events.map((ev, i) => (
                    <div key={i} className={styles.evidenceCard}>
                      <div className={styles.evidenceHead}>
                        <span className={styles.evidenceId}>{ev.report_number}</span>
                        <span className={styles.evidenceScore}>
                          {(ev.similarity_score * 100).toFixed(1)}% match
                        </span>
                      </div>
                      {(ev.manufacturer || ev.product_code) && (
                        <div className={styles.evidenceMeta}>
                          {[ev.manufacturer, ev.product_code, ev.date_received]
                            .filter(Boolean)
                            .join(' · ')}
                        </div>
                      )}
                      {ev.narrative_snippet && (
                        <p className={styles.evidenceText}>{ev.narrative_snippet}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {result.recalls && result.recalls.length > 0 && (
                <div className={styles.evidenceBlock}>
                  <h4>Related FDA Recalls (openFDA)</h4>
                  {result.recalls.map((rc, i) => (
                    <div key={i} className={styles.evidenceCard}>
                      <div className={styles.evidenceHead}>
                        <span className={styles.evidenceId}>{rc.recall_number}</span>
                        {rc.classification && (
                          <span className={styles.recallClass}>{rc.classification}</span>
                        )}
                      </div>
                      {(rc.recalling_firm || rc.recall_date) && (
                        <div className={styles.evidenceMeta}>
                          {[rc.recalling_firm, rc.recall_date].filter(Boolean).join(' · ')}
                        </div>
                      )}
                      {rc.reason_for_recall && (
                        <p className={styles.evidenceText}>{rc.reason_for_recall}</p>
                      )}
                    </div>
                  ))}
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
