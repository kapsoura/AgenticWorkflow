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

export interface AnalyzeResponse {
  report_id: string;
  report_type: string;
  risk_bucket: string;
  extraction: Record<string, unknown>;
  evidence_count: number;
  sections: { name: string; title: string; content: string }[];
  validation: { passed: boolean; issues: string[] };
  cluster?: Record<string, unknown>;
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
