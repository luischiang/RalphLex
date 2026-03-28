/** API client for RalphLex backend. */

export interface CaseListItem {
  id: string;
  title: string;
  status: "pending" | "running" | "completed" | "escalated";
  judicial_level: string;
  created_at: string;
}

export interface CaseResponse {
  id: string;
  title: string;
  facts: string;
  claimant_input: string | null;
  respondent_input: string | null;
  status: "pending" | "running" | "completed" | "escalated";
  judicial_level: string;
  created_at: string;
  updated_at: string;
}

export interface CaseSubmission {
  title: string;
  facts: string;
  party_role: "claimant" | "respondent";
  supporting_materials?: string;
}

export interface StatusResponse {
  case_id: string;
  status: string;
  phase: string;
  judicial_level: string;
  message: string;
}

export interface MCDAResult {
  criteria_scores: Record<string, Record<string, number>>;
  weighted_totals: Record<string, number>;
  predicted_winner: string | null;
  confidence: number;
}

export interface CourtEvaluation {
  consistency_scores: Record<string, number>;
  compliance_assessment: Record<string, string>;
  preliminary_opinion: string;
  adversarial_challenge: string;
  reconciled_decision: string;
  escalation_recommendation: string | null;
  escalation_decision: string | null;
  adversarial_review: Record<string, string>;
  reasoning_trace: string[];
}

export interface Argument {
  role: string;
  iteration: number;
  content: string;
  legal_basis: string[];
  factual_claims: string[];
  counterarguments: string[];
  evidence_requests: string[];
  references: string[];
  strategy_notes: string[];
  timestamp: string;
}

export interface TimelineEntry {
  timestamp: string;
  phase: string;
  event: string;
  details: Record<string, unknown>;
  is_escalation: boolean;
}

export interface EscalationDecision {
  should_escalate: boolean;
  reason: string;
  current_level: string;
  next_level: string;
  triggers: string[];
}

export interface FinalResult {
  judicial_stage: string;
  arguments_summary: Record<string, unknown[]>;
  referenced_precedents: string[];
  referenced_laws: string[];
  court_evaluation: Record<string, unknown>;
  escalation_decisions: EscalationDecision[];
  mcda_scoring: Record<string, unknown>;
  predicted_winner: string | null;
  confidence_estimate: number;
  full_reasoning_trace: string[];
  refinement_rounds: number;
}

export interface LevelCostBreakdown {
  level: string;
  attorney_fees_per_party_low: number;
  attorney_fees_per_party_high: number;
  court_costs_low: number;
  court_costs_high: number;
  expert_witness_fees_low: number;
  expert_witness_fees_high: number;
  duration_months_low: number;
  duration_months_high: number;
}

export interface CostEstimate {
  level_breakdowns: LevelCostBreakdown[];
  total_attorney_fees_per_party_low: number;
  total_attorney_fees_per_party_high: number;
  total_court_costs_low: number;
  total_court_costs_high: number;
  total_expert_fees_low: number;
  total_expert_fees_high: number;
  total_per_party_low: number;
  total_per_party_high: number;
  total_all_parties_low: number;
  total_all_parties_high: number;
  estimated_duration_months_low: number;
  estimated_duration_months_high: number;
  complexity_category: string;
  complexity_multiplier: number;
  argument_rounds: number;
  ralphlex_processing_seconds: number;
  ralphlex_cost_estimate: string;
  savings_low: number;
  savings_high: number;
}

export interface RunSampleResponse {
  case_id: string;
  template: string;
  monitor_url: string;
  status: string;
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function listCases(): Promise<CaseListItem[]> {
  return apiFetch<CaseListItem[]>("/api/cases");
}

export async function getCase(caseId: string): Promise<CaseResponse> {
  return apiFetch<CaseResponse>(`/api/cases/${caseId}`);
}

export async function createCase(
  submission: CaseSubmission,
): Promise<CaseResponse> {
  return apiFetch<CaseResponse>("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submission),
  });
}

export async function getCaseStatus(
  caseId: string,
): Promise<StatusResponse> {
  return apiFetch<StatusResponse>(`/api/cases/${caseId}/status`);
}

export async function getCaseTimeline(
  caseId: string,
): Promise<TimelineEntry[]> {
  return apiFetch<TimelineEntry[]>(`/api/cases/${caseId}/timeline`);
}

export async function runSampleCase(
  template: string = "contract",
): Promise<RunSampleResponse> {
  return apiFetch<RunSampleResponse>(
    `/api/tools/run-sample?template=${encodeURIComponent(template)}`,
    { method: "POST" },
  );
}

export async function getOutput<T>(
  caseId: string,
  filename: string,
): Promise<T | null> {
  try {
    const res = await fetch(`/api/cases/${caseId}/outputs/${filename}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
