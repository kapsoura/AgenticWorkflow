// Empty string in dev (Vite proxies /api and /health to the local FastAPI server,
// see vite.config.ts). Set at build time for production deploys, e.g. a Fly.io URL.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export interface StatsResponse {
  total_events: number;
  events_with_narrative: number;
  extracted_events: number;
  total_recalls: number;
  total_clusters: number;
}

export interface MetaResponse {
  product_codes: string[];
  event_types: string[];
  report_types: string[];
}

export interface TrendDataPoint {
  label: string;
  count: number;
}

export interface TrendsResponse {
  dimension: string;
  series: TrendDataPoint[];
}

export interface TemplateSection {
  section: string;
  keywords: string[];
}

export interface BlueprintSection {
  name: string;
  title: string;
}

export interface TemplatesResponse {
  section_catalog: TemplateSection[];
  blueprints: Record<string, BlueprintSection[]>;
}

export interface SimilarEvent {
  report_number: string;
  similarity_score: number;
  narrative_snippet?: string | null;
  product_code?: string | null;
  manufacturer?: string | null;
  device_name?: string | null;
  date_received?: number | string | null;
}

export interface RecallEvidence {
  recall_number: string;
  reason_for_recall: string;
  root_cause?: string | null;
  classification?: string | null;
  recalling_firm?: string | null;
  recall_date?: number | string | null;
}

export interface AnalyzeResponse {
  report_id: string;
  report_type: string;
  applicable_report_types?: string[];
  risk_bucket: string;
  guardrail?: { available?: boolean; input_rejected: boolean; reasons: string[] };
  risk?: {
    bucket: string;
    method: 'anthropic' | 'deterministic' | 'unavailable' | 'guardrail';
    report_type?: string;
    signals: string[];
    rationale: string;
    severity_level?: string | null;
    probability_level?: string | null;
    escalation_required?: boolean;
    prrc_notification_required?: boolean;
    capa_recommendation?: string | null;
    hazardous_situation?: string | null;
    harm?: string | null;
  };
  extraction: Record<string, unknown>;
  extraction_status?: { ok: boolean; reason?: string; message?: string };
  evidence_count: number;
  recalls?: RecallEvidence[];
  validation: { passed: boolean; issues: string[] };
  cluster?: Record<string, unknown> & {
    similar_events?: SimilarEvent[];
    cluster_id?: number | string | null;
    cluster_label?: string | null;
    trend_flag?: string | null;
    cluster_size?: number | null;
    growth_rate_30d?: number | null;
  };
  total_duration_ms?: number;
}

export interface HealthResponse {
  status: string;
  service: string;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return response.json();
}

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${BASE_URL}/health`);
    return await handleResponse<HealthResponse>(res);
  } catch {
    return { status: 'offline', service: '' };
  }
}

export async function fetchMeta(): Promise<MetaResponse> {
  const res = await fetch(`${BASE_URL}/api/meta`);
  return handleResponse<MetaResponse>(res);
}

export async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch(`${BASE_URL}/api/stats`);
  return handleResponse<StatsResponse>(res);
}

export async function fetchTrends(
  dimension: string,
  filters?: { product_code?: string; event_type?: string; software_related?: boolean }
): Promise<TrendsResponse> {
  const params = new URLSearchParams({ dimension });
  if (filters?.product_code) params.set('product_code', filters.product_code);
  if (filters?.event_type) params.set('event_type', filters.event_type);
  if (filters?.software_related !== undefined)
    params.set('software_related', String(filters.software_related));
  const res = await fetch(`${BASE_URL}/api/trends?${params}`);
  return handleResponse<TrendsResponse>(res);
}

export async function fetchTemplates(): Promise<TemplatesResponse> {
  const res = await fetch(`${BASE_URL}/api/templates`);
  return handleResponse<TemplatesResponse>(res);
}

export async function analyzeComplaint(data: {
  narrative: string;
  product_code: string;
  event_type: string;
  manufacturer: string;
}): Promise<AnalyzeResponse> {
  const params = new URLSearchParams({
    narrative: data.narrative,
    product_code: data.product_code,
    event_type: data.event_type,
    manufacturer: data.manufacturer,
  });
  const res = await fetch(`${BASE_URL}/api/analyze?${params}`, {
    method: 'POST',
  });
  return handleResponse<AnalyzeResponse>(res);
}

/**
 * Render a single agent-authored report to a Word (.docx) document on the
 * backend and return the binary blob for client-side download. Pass
 * ``reportType`` (PSUR / INCIDENT_ASSESSMENT / CAPA) to choose which report the
 * ReportGenerationAgent authors; omit it for the analysis's routed type.
 */
export async function downloadReportDocx(
  result: AnalyzeResponse,
  inputs: { narrative: string; product_code: string; event_type: string; manufacturer: string },
  reportType?: string
): Promise<Blob> {
  const query = reportType ? `?report_type=${encodeURIComponent(reportType)}` : '';
  const res = await fetch(`${BASE_URL}/api/analyze/report${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...result, ...inputs }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.blob();
}

/**
 * Generate the three separate reports (PSUR, Incident Assessment, CAPA) on the
 * backend and return them packaged as a single .zip blob for download.
 */
export async function downloadReportsZip(
  result: AnalyzeResponse,
  inputs: { narrative: string; product_code: string; event_type: string; manufacturer: string }
): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/api/analyze/reports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...result, ...inputs }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.blob();
}

export async function processComplaint(data: {
  narrative: string;
  report_id?: string;
  skip_extraction?: boolean;
}): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE_URL}/api/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      narrative: data.narrative,
      report_id: data.report_id || `UI-${Date.now()}`,
      skip_extraction: data.skip_extraction ?? false,
    }),
  });
  return handleResponse<Record<string, unknown>>(res);
}

export async function fetchClusters(): Promise<Record<string, unknown>[]> {
  const res = await fetch(`${BASE_URL}/api/clusters`);
  return handleResponse<Record<string, unknown>[]>(res);
}

export interface GraphNode {
  id: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  conditional: boolean;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export async function fetchGraph(): Promise<GraphResponse> {
  const res = await fetch(`${BASE_URL}/api/graph`);
  return handleResponse<GraphResponse>(res);
}

export interface StepEvent {
  step: string;
  status: 'processing' | 'success' | 'error' | 'skipped';
  duration_ms?: number;
  data: Record<string, unknown>;
}

export type StreamHandler = (event: string, data: Record<string, unknown>) => void;

/**
 * Stream the processing pipeline via Server-Sent Events so the UI can render
 * the agentic flow live, node-by-node. Parses the SSE frames from the fetch
 * body stream (EventSource only supports GET, so we read the stream manually).
 */
export async function streamProcess(
  data: {
    narrative: string;
    report_id?: string;
    skip_extraction?: boolean;
    product_code?: string;
  },
  onEvent: StreamHandler,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/process/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      narrative: data.narrative,
      report_id: data.report_id || `UI-${Date.now()}`,
      skip_extraction: data.skip_extraction ?? true,
      product_code: data.product_code ?? null,
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    const text = res.body ? await res.text() : '';
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      if (!frame.trim()) continue;
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) {
        try {
          onEvent(eventName, JSON.parse(dataLines.join('\n')));
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  }
}
