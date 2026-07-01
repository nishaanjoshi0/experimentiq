export interface Experiment {
  id: string;
  name: string;
  status: string;
  hypothesis: string;
  createdAt: string | null;
}

export interface ExperimentDesign {
  hypothesis: string;
  primary_metric: string;
  metric_rationale: string;
  guardrail_metrics: string[];
  unit_of_randomization: string;
  estimated_runtime_days: number;
  minimum_detectable_effect: number;
  tradeoffs: string[];
  clarifying_questions: string[];
  confidence: number;
}

export interface SRMResult {
  has_srm: boolean;
  chi_square_statistic: number;
  p_value: number;
  observed_counts: Record<string, number>;
  expected_counts: Record<string, number>;
}

export interface DataQualityResult {
  passed: boolean;
  checks: Record<string, boolean>;
  failure_reasons: string[];
}

export interface SequentialTestResult {
  can_stop: boolean;
  current_p_value: number;
  spending_boundary: number;
  information_fraction: number;
  recommendation: string;
}

export interface MonitoringReport {
  experiment_id: string;
  health_status: string;
  srm_check: SRMResult | null;
  data_quality: DataQualityResult | null;
  sequential_test: SequentialTestResult | null;
  novelty_check: {
    has_novelty: boolean;
    early_window_lift: number;
    overall_lift: number;
    novelty_ratio: number;
    early_window_days: number;
    message: string;
  } | null;
  summary: string;
  suggested_actions: string[];
  confidence: number;
}

export interface Recommendation {
  experiment_id: string;
  decision: string;
  confidence: number;
  primary_metric_summary: string;
  guardrail_summary: string;
  reasoning: string;
  follow_up_cuts: string[];
  risks: string[];
  data_quality_passed: boolean;
  created_at: string;
}

interface ExperimentApiPayload {
  id?: string;
  experiment_id?: string;
  name?: string;
  status?: string;
  hypothesis?: string;
  created_at?: string;
  createdAt?: string;
  dateCreated?: string;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T | { detail?: string };
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "Request failed.";
    throw new Error(detail);
  }
  return payload as T;
}

function normalizeExperiment(payload: ExperimentApiPayload): Experiment {
  return {
    id: payload.id ?? payload.experiment_id ?? "unknown",
    name: payload.name ?? "Untitled experiment",
    status: payload.status ?? "draft",
    hypothesis: payload.hypothesis ?? "No hypothesis provided.",
    createdAt: payload.created_at ?? payload.createdAt ?? payload.dateCreated ?? null
  };
}

export type ExperimentPlatform = "growthbook" | "launchdarkly" | "statsig";

export interface ExperimentPlatformStatus {
  connected: boolean;
  connected_at?: string;
}

export interface AllExperimentPlatformStatus {
  growthbook: ExperimentPlatformStatus;
  launchdarkly: ExperimentPlatformStatus;
  statsig: ExperimentPlatformStatus;
}

export async function listExperiments(platform: ExperimentPlatform = "growthbook"): Promise<Experiment[]> {
  const response = await fetch(`/api/experiments?platform=${platform}`, {
    method: "GET",
    cache: "no-store",
    credentials: "include"
  });
  const payload = await parseJsonResponse<ExperimentApiPayload[]>(response);
  return payload.map(normalizeExperiment);
}

export async function getExperimentPlatformStatuses(): Promise<AllExperimentPlatformStatus> {
  const response = await fetch("/api/experiments/platforms", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  return parseJsonResponse<AllExperimentPlatformStatus>(response);
}

export async function connectLaunchDarkly(
  access_token: string,
  project_key: string,
  environment_key: string
): Promise<{ connected: boolean }> {
  const response = await fetch("/api/experiments/platforms?platform=launchdarkly", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token, project_key, environment_key }),
  });
  return parseJsonResponse<{ connected: boolean }>(response);
}

export async function disconnectLaunchDarkly(): Promise<void> {
  await fetch("/api/experiments/platforms?platform=launchdarkly", {
    method: "DELETE",
    credentials: "include",
  });
}

export async function connectStatsig(server_secret: string): Promise<{ connected: boolean }> {
  const response = await fetch("/api/experiments/platforms?platform=statsig", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ server_secret }),
  });
  return parseJsonResponse<{ connected: boolean }>(response);
}

export async function disconnectStatsig(): Promise<void> {
  await fetch("/api/experiments/platforms?platform=statsig", {
    method: "DELETE",
    credentials: "include",
  });
}

export async function interpretExperiment(id: string): Promise<Recommendation> {
  const response = await fetch("/api/interpret", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ id })
  });
  return parseJsonResponse<Recommendation>(response);
}

export async function frameExperiment(hypothesis: string): Promise<ExperimentDesign> {
  const response = await fetch("/api/experiments/frame", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ hypothesis })
  });
  return parseJsonResponse<ExperimentDesign>(response);
}

export async function getMonitoringReport(id: string): Promise<MonitoringReport> {
  const response = await fetch(`/api/monitor?id=${encodeURIComponent(id)}`, {
    method: "GET",
    cache: "no-store",
    credentials: "include"
  });
  return parseJsonResponse<MonitoringReport>(response);
}

export interface ExperimentOpportunity {
  rank: number;
  title: string;
  hypothesis: string;
  primary_metric: string;
  estimated_lift_low_pct: number;
  estimated_lift_high_pct: number;
  risk_level: string;
  effort_level: string;
  evidence: string;
  expected_impact_score: number;
  segment_to_watch: string;
}

export interface OpportunityReport {
  opportunities: ExperimentOpportunity[];
  data_summary: Record<string, unknown>;
  analysis_context: string;
  generated_at: string;
  confidence: number;
  data_source: string;
}

export interface OpportunityRequest {
  company_description?: string;
  current_metrics?: Record<string, number>;
  data_source: "demo" | "csv";
  csv_content?: string;
}

export async function discoverOpportunities(
  request: OpportunityRequest
): Promise<OpportunityReport> {
  const response = await fetch("/api/opportunities", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonResponse<OpportunityReport>(response);
}

export interface DatasetMeta {
  id: string;
  name: string;
  description: string;
  size: string;
  use_case: string;
  download_url: string;
  download_instructions: string;
  columns_hint: string;
  industry: string;
}

export interface DatasetAnalyzeRequest {
  csv_content: string;
  dataset_type?: string;
  company_description?: string;
  current_metrics?: Record<string, number>;
}

export interface ConnectionStatus {
  connected: boolean;
  email?: string;
  property_id?: string;
  connected_at?: string;
}

export interface StartExperimentRequest {
  name: string;
  hypothesis: string;
  description?: string;
  tags?: string[];
}

export interface StartExperimentResponse {
  experiment_id: string;
  name: string;
  platform: string;
  platform_url: string;
  growthbook_url?: string;
}

export async function fetchDatasets(): Promise<DatasetMeta[]> {
  const response = await fetch("/api/datasets", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  return parseJsonResponse<DatasetMeta[]>(response);
}

export async function analyzeDataset(
  request: DatasetAnalyzeRequest
): Promise<OpportunityReport> {
  const response = await fetch("/api/datasets/analyze", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonResponse<OpportunityReport>(response);
}

export async function connectGA4(): Promise<{ auth_url: string }> {
  const response = await fetch("/api/auth/google", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  return parseJsonResponse<{ auth_url: string }>(response);
}

export async function getGA4Status(): Promise<ConnectionStatus> {
  const response = await fetch("/api/auth/status", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  return parseJsonResponse<ConnectionStatus>(response);
}

export async function disconnectGA4(): Promise<ConnectionStatus> {
  const response = await fetch("/api/auth/status", {
    method: "DELETE",
    credentials: "include",
  });
  return parseJsonResponse<ConnectionStatus>(response);
}

export async function getGA4Recommendations(
  payload: { company_description?: string; current_metrics?: Record<string, number> }
): Promise<OpportunityReport> {
  const response = await fetch("/api/analytics", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<OpportunityReport>(response);
}

export interface AllPlatformStatus {
  ga4: { connected: boolean };
  amplitude: { connected: boolean; connected_at?: string };
  mixpanel: { connected: boolean; connected_at?: string };
}

export async function getAllPlatformStatuses(): Promise<AllPlatformStatus> {
  const response = await fetch("/api/analytics/platforms", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  return parseJsonResponse<AllPlatformStatus>(response);
}

export async function connectAmplitude(api_key: string, api_secret: string): Promise<{ connected: boolean }> {
  const response = await fetch("/api/analytics/amplitude?action=connect", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key, api_secret }),
  });
  return parseJsonResponse<{ connected: boolean }>(response);
}

export async function disconnectAmplitude(): Promise<void> {
  await fetch("/api/analytics/amplitude", { method: "DELETE", credentials: "include" });
}

export async function getAmplitudeRecommendations(
  payload: { company_description?: string; current_metrics?: Record<string, number> }
): Promise<OpportunityReport> {
  const response = await fetch("/api/analytics/amplitude?action=recommendations", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<OpportunityReport>(response);
}

export async function connectMixpanel(username: string, secret: string, project_id?: string): Promise<{ connected: boolean }> {
  const response = await fetch("/api/analytics/mixpanel?action=connect", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, secret, project_id: project_id ?? "" }),
  });
  return parseJsonResponse<{ connected: boolean }>(response);
}

export async function disconnectMixpanel(): Promise<void> {
  await fetch("/api/analytics/mixpanel", { method: "DELETE", credentials: "include" });
}

export async function getMixpanelRecommendations(
  payload: { company_description?: string; current_metrics?: Record<string, number> }
): Promise<OpportunityReport> {
  const response = await fetch("/api/analytics/mixpanel?action=recommendations", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse<OpportunityReport>(response);
}

export async function startExperiment(
  request: StartExperimentRequest,
  platform: ExperimentPlatform = "growthbook"
): Promise<StartExperimentResponse> {
  const response = await fetch(`/api/experiments/start?platform=${platform}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonResponse<StartExperimentResponse>(response);
}
