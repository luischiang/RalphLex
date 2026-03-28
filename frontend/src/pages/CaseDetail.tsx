import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type {
  Argument,
  CaseResponse,
  CourtEvaluation,
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

export default function CaseDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const [caseData, setCaseData] = useState<CaseResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [iterations, setIterations] = useState<Argument[]>([]);
  const [courtEval, setCourtEval] = useState<CourtEvaluation | null>(null);
  const [mcda, setMcda] = useState<MCDAResult | null>(null);
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
    ])
      .then(([c, s, iters, court, mcdaRes]) => {
        setCaseData(c);
        setStatus(s);
        setIterations(iters);
        setCourtEval(court);
        setMcda(mcdaRes);
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
            {courtEval.reasoning_trace.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-1">
                  Reasoning Trace
                </h3>
                <ol className="list-decimal list-inside text-sm text-gray-600 space-y-1">
                  {courtEval.reasoning_trace.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
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
      {courtEval?.escalation_decision && (
        <Section title="Escalation History">
          <p className="text-sm text-gray-700">
            {courtEval.escalation_decision}
          </p>
        </Section>
      )}
    </div>
  );
}
