import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type {
  Argument,
  CaseResponse,
  CourtEvaluation,
  EscalationDecision,
  FinalResult,
  MCDAResult,
  StatusResponse,
} from "../api";
import { getCase, getCaseStatus } from "../api";
import StatusBadge from "../components/StatusBadge";

/** Fetch optional JSON from a case output path. Returns null on 404/error. */
async function fetchOutput<T>(caseId: string, file: string): Promise<T | null> {
  try {
    const res = await fetch(`/api/cases/${caseId}/outputs/${file}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Fetch all iteration files for a case. */
async function fetchIterations(caseId: string): Promise<Argument[]> {
  try {
    const res = await fetch(`/api/cases/${caseId}/iterations`);
    if (!res.ok) return [];
    return (await res.json()) as Argument[];
  } catch {
    return [];
  }
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <h2 className="text-lg font-semibold text-gray-900 mb-3 border-b border-gray-200 pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

function ArgumentCard({ arg }: { arg: Argument }) {
  const isClaimant = arg.role === "claimant";
  return (
    <div
      className={`rounded-lg border p-4 ${
        isClaimant
          ? "border-blue-200 bg-blue-50"
          : "border-red-200 bg-red-50"
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`text-xs font-semibold uppercase ${
            isClaimant ? "text-blue-700" : "text-red-700"
          }`}
        >
          {arg.role}
        </span>
        <span className="text-xs text-gray-500">
          Round {arg.iteration}
        </span>
      </div>
      <p className="text-sm text-gray-800 whitespace-pre-wrap mb-3">
        {arg.content}
      </p>
      {arg.legal_basis.length > 0 && (
        <div className="mb-2">
          <span className="text-xs font-medium text-gray-600">
            Legal Basis:
          </span>
          <ul className="list-disc list-inside text-xs text-gray-600 ml-2">
            {arg.legal_basis.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}
      {arg.factual_claims.length > 0 && (
        <div className="mb-2">
          <span className="text-xs font-medium text-gray-600">
            Factual Claims:
          </span>
          <ul className="list-disc list-inside text-xs text-gray-600 ml-2">
            {arg.factual_claims.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {arg.counterarguments.length > 0 && (
        <div>
          <span className="text-xs font-medium text-gray-600">
            Counterarguments:
          </span>
          <ul className="list-disc list-inside text-xs text-gray-600 ml-2">
            {arg.counterarguments.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MCDATable({ mcda }: { mcda: MCDAResult }) {
  const criteria = Object.keys(mcda.criteria_scores);
  return (
    <div>
      <div className="overflow-hidden rounded-lg border border-gray-200 mb-4">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Criterion
              </th>
              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                Claimant
              </th>
              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                Respondent
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {criteria.map((c) => (
              <tr key={c}>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {c.replace(/_/g, " ")}
                </td>
                <td className="px-4 py-2 text-sm text-right font-mono">
                  {mcda.criteria_scores[c]?.claimant?.toFixed(1) ?? "-"}
                </td>
                <td className="px-4 py-2 text-sm text-right font-mono">
                  {mcda.criteria_scores[c]?.respondent?.toFixed(1) ?? "-"}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-gray-50">
            <tr className="font-semibold">
              <td className="px-4 py-2 text-sm">Weighted Total</td>
              <td className="px-4 py-2 text-sm text-right font-mono">
                {mcda.weighted_totals.claimant?.toFixed(3) ?? "-"}
              </td>
              <td className="px-4 py-2 text-sm text-right font-mono">
                {mcda.weighted_totals.respondent?.toFixed(3) ?? "-"}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="flex gap-6 text-sm">
        <div>
          <span className="text-gray-500">Predicted Winner: </span>
          <span className="font-semibold text-gray-900">
            {mcda.predicted_winner ?? "N/A"}
          </span>
        </div>
        <div>
          <span className="text-gray-500">Confidence: </span>
          <span className="font-semibold text-gray-900">
            {(mcda.confidence * 100).toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}

function ConsistencyScores({
  scores,
}: {
  scores: Record<string, number>;
}) {
  const entries = Object.entries(scores);
  if (entries.length === 0) return <p className="text-sm text-gray-500">No consistency scores available.</p>;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {entries.map(([party, score]) => (
        <div key={party} className="rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 capitalize">
              {party}
            </span>
            <span className="text-sm font-semibold text-gray-900">
              {typeof score === "number" ? score.toFixed(1) : String(score)}
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5">
            <div
              className={`h-2.5 rounded-full ${
                party === "claimant" ? "bg-blue-600" : "bg-red-600"
              }`}
              style={{
                width: `${Math.min(100, (typeof score === "number" ? score : 0) * 10)}%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ComplianceAssessment({
  assessment,
}: {
  assessment: Record<string, string>;
}) {
  const entries = Object.entries(assessment);
  if (entries.length === 0) return <p className="text-sm text-gray-500">No compliance data available.</p>;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {entries.map(([party, text]) => (
        <div
          key={party}
          className={`rounded-lg border p-4 ${
            party === "claimant"
              ? "border-blue-200 bg-blue-50"
              : "border-red-200 bg-red-50"
          }`}
        >
          <h4 className="text-sm font-medium text-gray-700 capitalize mb-2">
            {party}
          </h4>
          <p className="text-sm text-gray-600 whitespace-pre-wrap">
            {String(text)}
          </p>
        </div>
      ))}
    </div>
  );
}

function EscalationCards({
  decisions,
  judicialStage,
}: {
  decisions: EscalationDecision[];
  judicialStage: string;
}) {
  if (decisions.length === 0) {
    return (
      <p className="text-sm text-gray-600 bg-gray-50 rounded-lg p-4">
        No escalation — resolved at{" "}
        <span className="font-medium">{judicialStage}</span>
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {decisions.map((d, i) => (
        <div
          key={i}
          className="rounded-lg border border-amber-300 bg-amber-50 p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold text-amber-800">
              {d.current_level}
            </span>
            <span className="text-amber-600">&rarr;</span>
            <span className="text-sm font-semibold text-amber-800">
              {d.next_level}
            </span>
          </div>
          <p className="text-sm text-amber-700 mb-2">{d.reason}</p>
          {d.triggers.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {d.triggers.map((t, j) => (
                <span
                  key={j}
                  className="text-xs bg-amber-200 text-amber-800 rounded px-2 py-0.5"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function PerLevelEvaluations({
  caseId,
  decisions,
}: {
  caseId: string;
  decisions: EscalationDecision[];
}) {
  const [levelEvals, setLevelEvals] = useState<
    { level: string; eval: CourtEvaluation }[]
  >([]);
  const [openLevel, setOpenLevel] = useState<string | null>(null);

  useEffect(() => {
    if (decisions.length === 0) return;
    const levels = decisions.map((d) =>
      d.current_level.toLowerCase().replace(/\s+/g, "_"),
    );
    Promise.all(
      levels.map(async (slug, i) => {
        const ev = await fetchOutput<CourtEvaluation>(
          caseId,
          `level_${slug}/court_evaluation.json`,
        );
        return ev ? { level: decisions[i].current_level, eval: ev } : null;
      }),
    ).then((results) => {
      setLevelEvals(
        results.filter(
          (r): r is { level: string; eval: CourtEvaluation } => r !== null,
        ),
      );
    });
  }, [caseId, decisions]);

  if (levelEvals.length === 0) return null;

  return (
    <Section title="Per-Level Evaluations">
      <div className="space-y-2">
        {levelEvals.map(({ level, eval: ev }) => (
          <div key={level} className="border border-gray-200 rounded-lg">
            <button
              className="w-full text-left px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 flex items-center justify-between"
              onClick={() =>
                setOpenLevel(openLevel === level ? null : level)
              }
            >
              <span>{level} Evaluation</span>
              <span className="text-gray-400">
                {openLevel === level ? "\u25B2" : "\u25BC"}
              </span>
            </button>
            {openLevel === level && (
              <div className="px-4 pb-4 space-y-3">
                {ev.preliminary_opinion && (
                  <div>
                    <h4 className="text-xs font-medium text-gray-600 mb-1">
                      Preliminary Opinion
                    </h4>
                    <p className="text-sm text-gray-600 whitespace-pre-wrap bg-gray-50 rounded p-2">
                      {ev.preliminary_opinion}
                    </p>
                  </div>
                )}
                {ev.adversarial_challenge && (
                  <div>
                    <h4 className="text-xs font-medium text-gray-600 mb-1">
                      Adversarial Challenge
                    </h4>
                    <p className="text-sm text-gray-600 whitespace-pre-wrap bg-yellow-50 rounded p-2">
                      {ev.adversarial_challenge}
                    </p>
                  </div>
                )}
                {ev.reconciled_decision && (
                  <div>
                    <h4 className="text-xs font-medium text-gray-600 mb-1">
                      Reconciled Decision
                    </h4>
                    <p className="text-sm text-gray-600 whitespace-pre-wrap bg-green-50 rounded p-2">
                      {ev.reconciled_decision}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

export default function CaseDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseData, setCaseData] = useState<CaseResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [iterations, setIterations] = useState<Argument[]>([]);
  const [courtEval, setCourtEval] = useState<CourtEvaluation | null>(null);
  const [mcda, setMcda] = useState<MCDAResult | null>(null);
  const [finalResult, setFinalResult] = useState<FinalResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId) return;
    Promise.all([
      getCase(caseId),
      getCaseStatus(caseId),
      fetchIterations(caseId),
      fetchOutput<CourtEvaluation>(caseId, "court_evaluation.json"),
      fetchOutput<MCDAResult>(caseId, "mcda_scoring.json"),
      fetchOutput<FinalResult>(caseId, "final_result.json"),
    ])
      .then(([c, s, iters, court, mcdaRes, fr]) => {
        setCaseData(c);
        setStatus(s);
        setIterations(iters);
        setCourtEval(court);
        setMcda(mcdaRes);
        setFinalResult(fr);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setLoading(false));
  }, [caseId]);

  if (loading) return <p className="p-6 text-gray-500">Loading...</p>;
  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!caseData) return <p className="p-6 text-gray-500">Case not found.</p>;

  // Group iterations by round
  const rounds = new Map<number, Argument[]>();
  for (const arg of iterations) {
    const list = rounds.get(arg.iteration) ?? [];
    list.push(arg);
    rounds.set(arg.iteration, list);
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold text-gray-900">
            {caseData.title}
          </h1>
          <StatusBadge status={caseData.status} />
        </div>
        <div className="flex gap-6 text-sm text-gray-500">
          <span>ID: {caseData.id}</span>
          <span>Level: {caseData.judicial_level}</span>
          <span>Created: {new Date(caseData.created_at).toLocaleString()}</span>
        </div>
        {status && status.phase !== "pending" && (
          <div className="mt-2 text-sm text-gray-600">
            Phase: <span className="font-medium">{status.phase}</span>
            {" — "}
            {status.message}
          </div>
        )}
      </div>

      {/* Outcome Summary */}
      {finalResult && (
        <div className="mb-8 rounded-lg border border-green-200 bg-green-50 p-5">
          <h2 className="text-sm font-medium text-green-800 mb-3 uppercase tracking-wide">
            Outcome Summary
          </h2>
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <span className="text-sm text-green-700">Predicted Winner</span>
              <p className="text-xl font-bold text-green-900 capitalize">
                {finalResult.predicted_winner ?? "Undetermined"}
              </p>
            </div>
            <div>
              <span className="text-sm text-green-700">Confidence</span>
              <p className="text-xl font-bold text-green-900">
                {(finalResult.confidence_estimate * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <span className="text-sm text-green-700">Judicial Stage</span>
              <p className="text-xl font-bold text-green-900">
                {finalResult.judicial_stage}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Facts */}
      <Section title="Case Facts">
        <p className="text-sm text-gray-700 whitespace-pre-wrap">
          {caseData.facts}
        </p>
      </Section>

      {/* Arguments */}
      {iterations.length > 0 && (
        <Section title="Arguments">
          <div className="space-y-6">
            {Array.from(rounds.entries())
              .sort(([a], [b]) => a - b)
              .map(([round, args]) => (
                <div key={round}>
                  <h3 className="text-sm font-medium text-gray-500 mb-2">
                    Round {round}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {args
                      .sort((a, b) => a.role.localeCompare(b.role))
                      .map((arg, i) => (
                        <ArgumentCard key={i} arg={arg} />
                      ))}
                  </div>
                </div>
              ))}
          </div>
        </Section>
      )}

      {/* Consistency Scores */}
      {courtEval && courtEval.consistency_scores && (
        <Section title="Consistency Scores">
          <ConsistencyScores scores={courtEval.consistency_scores} />
        </Section>
      )}

      {/* Compliance Assessment */}
      {courtEval && courtEval.compliance_assessment && (
        <Section title="Compliance Assessment">
          <ComplianceAssessment assessment={courtEval.compliance_assessment} />
        </Section>
      )}

      {/* Court Evaluation */}
      {courtEval && (
        <Section title="Court Evaluation">
          <div className="space-y-4">
            {courtEval.preliminary_opinion && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-1">
                  Preliminary Opinion
                </h3>
                <p className="text-sm text-gray-600 whitespace-pre-wrap bg-gray-50 rounded p-3">
                  {courtEval.preliminary_opinion}
                </p>
              </div>
            )}
            {courtEval.adversarial_challenge && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-1">
                  Adversarial Challenge
                </h3>
                <p className="text-sm text-gray-600 whitespace-pre-wrap bg-yellow-50 rounded p-3">
                  {courtEval.adversarial_challenge}
                </p>
              </div>
            )}
            {courtEval.reconciled_decision && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-1">
                  Reconciled Decision
                </h3>
                <p className="text-sm text-gray-600 whitespace-pre-wrap bg-green-50 rounded p-3">
                  {courtEval.reconciled_decision}
                </p>
              </div>
            )}
            {courtEval.escalation_recommendation && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-1">
                  Escalation Recommendation
                </h3>
                <p className="text-sm text-orange-700 bg-orange-50 rounded p-3">
                  {courtEval.escalation_recommendation}
                </p>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* MCDA Scores */}
      {mcda && (
        <Section title="MCDA Scoring">
          <MCDATable mcda={mcda} />
        </Section>
      )}

      {/* Escalation History */}
      {finalResult ? (
        <Section title="Escalation History">
          <EscalationCards
            decisions={finalResult.escalation_decisions}
            judicialStage={finalResult.judicial_stage}
          />
        </Section>
      ) : (
        courtEval?.escalation_decision && (
          <Section title="Escalation History">
            <p className="text-sm text-gray-700">
              {courtEval.escalation_decision}
            </p>
          </Section>
        )
      )}

      {/* Per-Level Evaluations */}
      {caseId && finalResult && finalResult.escalation_decisions.length > 0 && (
        <PerLevelEvaluations
          caseId={caseId}
          decisions={finalResult.escalation_decisions}
        />
      )}

      {/* Referenced Precedents & Laws */}
      {finalResult && (
        <Section title="Referenced Precedents & Laws">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">
                Precedents
              </h3>
              {finalResult.referenced_precedents.length > 0 ? (
                <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                  {finalResult.referenced_precedents.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-500">No references found</p>
              )}
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">Laws</h3>
              {finalResult.referenced_laws.length > 0 ? (
                <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                  {finalResult.referenced_laws.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-500">No references found</p>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* Full Reasoning Trace */}
      {finalResult && finalResult.full_reasoning_trace.length > 0 && (
        <Section title="Full Reasoning Trace">
          <ol className="list-decimal list-inside text-sm text-gray-600 space-y-2 bg-gray-50 rounded-lg p-4">
            {finalResult.full_reasoning_trace.map((step, i) => (
              <li key={i} className="leading-relaxed">
                {step}
              </li>
            ))}
          </ol>
        </Section>
      )}
    </div>
  );
}
