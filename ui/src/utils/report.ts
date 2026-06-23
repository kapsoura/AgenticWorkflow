import type { AnalyzeResponse } from '../api/client';
import type { AnalysisInputs } from '../context/AnalysisContext';

function methodLabel(method?: string): string {
  if (method === 'anthropic') return 'LLM (Anthropic)';
  if (method === 'deterministic') return 'Deterministic ISO 14971';
  return 'Unavailable';
}

/**
 * Build a structured, human-readable Markdown report from an analysis result.
 * Generated entirely client-side — no LLM or extra request required.
 */
export function buildReportMarkdown(
  result: AnalyzeResponse,
  inputs: AnalysisInputs
): string {
  const lines: string[] = [];
  const risk = result.risk;

  lines.push(`# Signal Intelligence Report`);
  lines.push('');
  lines.push(`**Report ID:** ${result.report_id}`);
  lines.push(`**Report type:** ${result.report_type ?? '—'}`);
  lines.push(`**Generated:** ${new Date().toISOString()}`);
  lines.push('');

  lines.push(`## Complaint`);
  lines.push('');
  lines.push(`- **Product code:** ${inputs.productCode || '—'}`);
  lines.push(`- **Event type:** ${inputs.eventType || '—'}`);
  lines.push(`- **Manufacturer:** ${inputs.manufacturer || 'Unknown'}`);
  lines.push('');
  lines.push(`> ${inputs.narrative || '—'}`);
  lines.push('');

  lines.push(`## Risk Assessment (ISO 14971)`);
  lines.push('');
  lines.push(`- **Risk bucket:** ${result.risk_bucket ?? '—'}`);
  lines.push(`- **Method:** ${methodLabel(risk?.method)}`);
  if (risk?.severity_level) lines.push(`- **Severity:** ${risk.severity_level}`);
  if (risk?.probability_level) lines.push(`- **Probability:** ${risk.probability_level}`);
  if (risk?.hazardous_situation) lines.push(`- **Hazardous situation:** ${risk.hazardous_situation}`);
  if (risk?.harm) lines.push(`- **Harm:** ${risk.harm}`);
  if (risk?.escalation_required !== undefined)
    lines.push(`- **Escalation required:** ${risk.escalation_required ? 'Yes' : 'No'}`);
  if (risk?.prrc_notification_required !== undefined)
    lines.push(`- **PRRC notification:** ${risk.prrc_notification_required ? 'Yes' : 'No'}`);
  lines.push('');
  if (risk?.rationale) {
    lines.push(`**Rationale:** ${risk.rationale}`);
    lines.push('');
  }
  if (risk?.signals && risk.signals.length > 0) {
    lines.push(`**Signals:**`);
    risk.signals.forEach((s) => lines.push(`- ${s}`));
    lines.push('');
  }
  if (risk?.capa_recommendation) {
    lines.push(`## CAPA Recommendation`);
    lines.push('');
    lines.push(risk.capa_recommendation);
    lines.push('');
  }

  const similar = result.cluster?.similar_events ?? [];
  if (similar.length > 0) {
    lines.push(`## Retrieved Similar Events`);
    lines.push('');
    similar.forEach((ev) => {
      const pct =
        typeof ev.similarity_score === 'number'
          ? `${(ev.similarity_score * 100).toFixed(1)}%`
          : '—';
      const meta = [ev.manufacturer, ev.product_code, ev.date_received]
        .filter(Boolean)
        .join(' · ');
      lines.push(`- **${ev.report_number}** (${pct} match)${meta ? ` — ${meta}` : ''}`);
      if (ev.narrative_snippet) lines.push(`  - ${ev.narrative_snippet}`);
    });
    lines.push('');
  }

  if (result.recalls && result.recalls.length > 0) {
    lines.push(`## Related FDA Recalls (openFDA)`);
    lines.push('');
    result.recalls.forEach((rc) => {
      const meta = [rc.classification, rc.recalling_firm, rc.recall_date]
        .filter(Boolean)
        .join(' · ');
      lines.push(`- **${rc.recall_number}**${meta ? ` — ${meta}` : ''}`);
      if (rc.reason_for_recall) lines.push(`  - ${rc.reason_for_recall}`);
    });
    lines.push('');
  }

  const cluster = result.cluster;
  if (cluster) {
    lines.push(`## Cluster Assignment`);
    lines.push('');
    lines.push(`- **Cluster ID:** ${cluster.cluster_id ?? '—'}`);
    lines.push(`- **Cluster label:** ${cluster.cluster_label ?? '—'}`);
    lines.push(`- **Trend flag:** ${cluster.trend_flag ?? '—'}`);
    lines.push(`- **Cluster size:** ${cluster.cluster_size ?? '—'}`);
    lines.push(`- **30-day growth rate:** ${cluster.growth_rate_30d ?? '—'}`);
    lines.push('');
  }

  if (result.sections && result.sections.length > 0) {
    lines.push(`## Report Sections`);
    lines.push('');
    result.sections.forEach((sec) => {
      lines.push(`### ${sec.title || sec.name}`);
      lines.push('');
      lines.push(sec.content);
      lines.push('');
    });
  }

  return lines.join('\n');
}
