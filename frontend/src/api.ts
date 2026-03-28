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
