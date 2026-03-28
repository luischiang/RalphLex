import { useEffect, useRef, useState } from "react";
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
import CaseProgress from "../components/CaseProgress";
import StatusBadge from "../components/StatusBadge";

/* ===== Helpers ===== */

async function fetchOutput<T>(caseId: string, file: string): Promise<T | null> {
  try {
    const res = await fetch(`/api/cases/${caseId}/outputs/${file}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

async function fetchIterations(caseId: string): Promise<Argument[]> {
  try {
    const res = await fetch(`/api/cases/${caseId}/iterations`);
    if (!res.ok) return [];
    return (await res.json()) as Argument[];
  } catch {
    return [];
  }
}

/** Hook: triggers when element scrolls into view. */
function useInView<T extends HTMLElement>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          obs.disconnect();
        }
      },
      { threshold: 0.15 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return [ref, visible];
}

/** Hook: count-up animation for numbers. */
function useCountUp(target: number, duration: number, active: boolean): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!active) return;
    const start = performance.now();
    let raf: number;
    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(eased * target);
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, active]);

  return active ? value : target;
}

/* ===== Section Wrapper ===== */

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`mb-8 ${className ?? ""}`}>
      <h2 className="text-lg font-semibold text-[var(--color-navy-800)] font-[var(--font-serif)] mb-3 border-b border-[var(--color-gold-500)]/30 pb-2">
        {title}
      </h2>
      {children}
    </section>
  );
}

/* ===== Argument Card (courtroom debate style) ===== */

function ArgumentCard({ arg, side }: { arg: Argument; side: "left" | "right" }) {
  const isClaimant = arg.role === "claimant";
  return (
    <div
      className={`rounded-lg border-2 p-4 ${
        isClaimant
          ? "border-blue-800/30 bg-blue-900/5"
          : "border-red-900/30 bg-red-900/5"
      } ${side === "left" ? "animate-slide-left" : "animate-slide-right"}`}
      style={{ animationDelay: `${arg.iteration * 80}ms` }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`text-xs font-bold uppercase tracking-wider ${
            isClaimant ? "text-blue-800" : "text-red-800"
          }`}
        >
          {arg.role}
        </span>
        <span className="text-xs text-gray-400 font-mono">
          Round {arg.iteration}
        </span>
      </div>
      <p className="text-sm text-gray-800 whitespace-pre-wrap mb-3 leading-relaxed">
        {arg.content}
      </p>
      {arg.legal_basis.length > 0 && (
        <div className="mb-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Legal Basis
          </span>
          <ul className="list-disc list-inside text-xs text-gray-600 ml-2 mt-1">
            {arg.legal_basis.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}
      {arg.factual_claims.length > 0 && (
        <div className="mb-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Factual Claims
          </span>
          <ul className="list-disc list-inside text-xs text-gray-600 ml-2 mt-1">
            {arg.factual_claims.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {arg.counterarguments.length > 0 && (
        <div>
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Counterarguments
          </span>
          <ul className="list-disc list-inside text-xs text-gray-600 ml-2 mt-1">
            {arg.counterarguments.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ===== Gavel Divider ===== */

function GavelDivider() {
  return (
    <div className="flex items-center justify-center my-1">
      <svg
        className="w-5 h-5 text-[var(--color-gold-500)]"
        viewBox="0 0 24 24"
        fill="currentColor"
      >
        <path d="M12 2L9 5h6l-3-3zm-4 6l-5 5 1.4 1.4L9 9.8V20h2V9.8l4.6 4.6L17 13l-5-5H8z" />
      </svg>
    </div>
  );
}

/* ===== Animated MCDA Table ===== */

function AnimatedMCDATable({ mcda }: { mcda: MCDAResult }) {
  const criteria = Object.keys(mcda.criteria_scores);
  const [ref, visible] = useInView<HTMLDivElement>();
  const confidence = useCountUp(mcda.confidence * 100, 1000, visible);

  return (
    <div ref={ref}>
      <div className="overflow-hidden rounded-lg border border-[var(--color-navy-800)]/20 mb-4">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-[var(--color-navy-900)]">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-medium text-[var(--color-gold-400)] uppercase tracking-wider">
                Criterion
              </th>
              <th className="px-4 py-2.5 text-xs font-medium text-blue-300 uppercase tracking-wider w-1/3">
                Claimant
              </th>
              <th className="px-4 py-2.5 text-xs font-medium text-red-300 uppercase tracking-wider w-1/3">
                Respondent
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {criteria.map((c) => {
              const claimant = mcda.criteria_scores[c]?.claimant ?? 0;
              const respondent = mcda.criteria_scores[c]?.respondent ?? 0;
              const maxScore = 10;
              return (
                <tr key={c}>
                  <td className="px-4 py-2.5 text-sm text-gray-700 capitalize">
                    {c.replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-100 rounded-full h-2.5 overflow-hidden">
                        <div
                          className={`h-full bg-blue-600 rounded-full ${visible ? "animate-bar-grow" : ""}`}
                          style={{ width: `${(claimant / maxScore) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-gray-600 w-8 text-right">
                        {claimant.toFixed(1)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-100 rounded-full h-2.5 overflow-hidden">
                        <div
                          className={`h-full bg-red-600 rounded-full ${visible ? "animate-bar-grow" : ""}`}
                          style={{ width: `${(respondent / maxScore) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-gray-600 w-8 text-right">
                        {respondent.toFixed(1)}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="bg-gray-50">
            <tr className="font-semibold">
              <td className="px-4 py-2.5 text-sm text-[var(--color-navy-800)]">
                Weighted Total
              </td>
              <td className="px-4 py-2.5 text-sm text-center font-mono text-blue-700">
                {mcda.weighted_totals.claimant?.toFixed(3) ?? "-"}
              </td>
              <td className="px-4 py-2.5 text-sm text-center font-mono text-red-700">
                {mcda.weighted_totals.respondent?.toFixed(3) ?? "-"}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-gray-500">Predicted Winner:</span>
          <span className="font-bold text-[var(--color-navy-800)] capitalize text-base">
            {mcda.predicted_winner ?? "N/A"}
          </span>
          {mcda.predicted_winner && visible && (
            <span className="animate-bounce-in text-lg" role="img" aria-label="trophy">
              &#x1f3c6;
            </span>
          )}
        </div>
        <div>
          <span className="text-gray-500">Confidence: </span>
          <span className="font-bold text-[var(--color-navy-800)] text-base">
            {confidence.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
}

/* ===== Court Evaluation Reveal ===== */

function CourtEvalReveal({ courtEval }: { courtEval: CourtEvaluation }) {
  const [ref, visible] = useInView<HTMLDivElement>();

  return (
    <div ref={ref} className={`space-y-4 ${visible ? "" : "opacity-0"}`}>
      {courtEval.preliminary_opinion && (
        <div
          className={`rounded-lg p-4 bg-[var(--color-parchment)] border border-[var(--color-gold-500)]/30 ${visible ? "animate-fade-in" : ""}`}
        >
          <h3 className="text-sm font-semibold text-[var(--color-navy-800)] font-[var(--font-serif)] mb-2">
            Preliminary Opinion
          </h3>
          <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
            {courtEval.preliminary_opinion}
          </p>
        </div>
      )}
      {courtEval.adversarial_challenge && (
        <div
          className={`rounded-lg p-4 bg-amber-50 border border-amber-200 ${visible ? "animate-slide-right" : ""}`}
          style={{ animationDelay: "300ms" }}
        >
          <h3 className="text-sm font-semibold text-amber-800 font-[var(--font-serif)] mb-2">
            Adversarial Challenge
          </h3>
          <p className="text-sm text-amber-900 whitespace-pre-wrap leading-relaxed">
            {courtEval.adversarial_challenge}
          </p>
        </div>
      )}
      {courtEval.reconciled_decision && (
        <div
          className={`rounded-lg p-4 bg-emerald-50 border-2 border-emerald-300 ${visible ? "animate-gavel-drop" : ""}`}
          style={{ animationDelay: "600ms" }}
        >
          <div className={`${visible ? "animate-gavel-shake" : ""}`} style={{ animationDelay: "900ms" }}>
            <h3 className="text-sm font-semibold text-emerald-800 font-[var(--font-serif)] mb-2">
              Reconciled Decision
            </h3>
            <p className="text-sm text-emerald-900 whitespace-pre-wrap leading-relaxed">
              {courtEval.reconciled_decision}
            </p>
          </div>
        </div>
      )}
      {courtEval.escalation_recommendation && (
        <div className="rounded-lg p-3 bg-orange-50 border border-orange-200 animate-fade-in" style={{ animationDelay: "800ms" }}>
          <h3 className="text-sm font-medium text-orange-700 mb-1">
            Escalation Recommendation
          </h3>
          <p className="text-sm text-orange-800">
            {courtEval.escalation_recommendation}
          </p>
        </div>
      )}
    </div>
  );
}

/* ===== Consistency Scores ===== */

function ConsistencyScores({
  scores,
}: {
  scores: Record<string, number>;
}) {
  const entries = Object.entries(scores);
  const [ref, visible] = useInView<HTMLDivElement>();

  if (entries.length === 0)
    return <p className="text-sm text-gray-500">No consistency scores available.</p>;

  return (
    <div ref={ref} className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {entries.map(([party, score]) => (
        <div
          key={party}
          className={`rounded-lg border-2 p-4 ${
            party === "claimant"
              ? "border-blue-800/20 bg-blue-900/5"
              : "border-red-900/20 bg-red-900/5"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <span
              className={`text-sm font-bold uppercase tracking-wider ${
                party === "claimant" ? "text-blue-800" : "text-red-800"
              }`}
            >
              {party}
            </span>
            <span className="text-sm font-bold text-[var(--color-navy-800)]">
              {typeof score === "number" ? score.toFixed(1) : String(score)}
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
            <div
              className={`h-full rounded-full ${
                party === "claimant" ? "bg-blue-600" : "bg-red-600"
              } ${visible ? "animate-bar-grow" : ""}`}
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

/* ===== Compliance Assessment ===== */

function ComplianceAssessment({
  assessment,
}: {
  assessment: Record<string, string>;
}) {
  const entries = Object.entries(assessment);
  if (entries.length === 0)
    return <p className="text-sm text-gray-500">No compliance data available.</p>;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {entries.map(([party, text]) => (
        <div
          key={party}
          className={`rounded-lg border-2 p-4 ${
            party === "claimant"
              ? "border-blue-800/20 bg-blue-900/5"
              : "border-red-900/20 bg-red-900/5"
          }`}
        >
          <h4
            className={`text-sm font-bold uppercase tracking-wider mb-2 ${
              party === "claimant" ? "text-blue-800" : "text-red-800"
            }`}
          >
            {party}
          </h4>
          <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
            {String(text)}
          </p>
        </div>
      ))}
    </div>
  );
}

/* ===== Escalation Cards ===== */

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
        <span className="font-semibold">{judicialStage}</span>
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {decisions.map((d, i) => (
        <div
          key={i}
          className="rounded-lg border-2 border-amber-400 bg-amber-50 p-4 animate-fade-in"
          style={{ animationDelay: `${i * 150}ms` }}
        >
          <div className="flex items-center gap-3 mb-2">
            <span className="text-sm font-bold text-amber-900 bg-amber-200 rounded px-2 py-0.5">
              {d.current_level}
            </span>
            <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
            <span className="text-sm font-bold text-amber-900 bg-amber-200 rounded px-2 py-0.5">
              {d.next_level}
            </span>
          </div>
          <p className="text-sm text-amber-800 mb-2">{d.reason}</p>
          {d.triggers.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {d.triggers.map((t, j) => (
                <span
                  key={j}
                  className="text-xs bg-amber-200 text-amber-900 rounded-full px-2.5 py-0.5 font-medium"
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

/* ===== Per-Level Evaluations ===== */

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
          <div key={level} className="border-2 border-[var(--color-navy-800)]/10 rounded-lg overflow-hidden">
            <button
              className="w-full text-left px-4 py-3 text-sm font-semibold text-[var(--color-navy-800)] hover:bg-gray-50 flex items-center justify-between transition-colors"
              onClick={() =>
                setOpenLevel(openLevel === level ? null : level)
              }
            >
              <span className="font-[var(--font-serif)]">{level} Evaluation</span>
              <span className="text-gray-400 text-xs">
                {openLevel === level ? "\u25B2" : "\u25BC"}
              </span>
            </button>
            {openLevel === level && (
              <div className="px-4 pb-4 space-y-3 animate-fade-in">
                {ev.preliminary_opinion && (
                  <div className="rounded p-3 bg-[var(--color-parchment)]">
                    <h4 className="text-xs font-semibold text-gray-600 mb-1">
                      Preliminary Opinion
                    </h4>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">
                      {ev.preliminary_opinion}
                    </p>
                  </div>
                )}
                {ev.adversarial_challenge && (
                  <div className="rounded p-3 bg-amber-50">
                    <h4 className="text-xs font-semibold text-amber-700 mb-1">
                      Adversarial Challenge
                    </h4>
                    <p className="text-sm text-amber-900 whitespace-pre-wrap">
                      {ev.adversarial_challenge}
                    </p>
                  </div>
                )}
                {ev.reconciled_decision && (
                  <div className="rounded p-3 bg-emerald-50">
                    <h4 className="text-xs font-semibold text-emerald-700 mb-1">
                      Reconciled Decision
                    </h4>
                    <p className="text-sm text-emerald-900 whitespace-pre-wrap">
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

/* ===== Main Component ===== */

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

  if (loading)
    return (
      <p className="p-6 text-gray-500">Loading...</p>
    );
  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!caseData) return <p className="p-6 text-gray-500">Case not found.</p>;

  // Group iterations by round
  const rounds = new Map<number, Argument[]>();
  for (const arg of iterations) {
    const list = rounds.get(arg.iteration) ?? [];
    list.push(arg);
    rounds.set(arg.iteration, list);
  }

  const hasEscalation =
    finalResult != null && finalResult.escalation_decisions.length > 0;

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold text-[var(--color-navy-800)] font-[var(--font-serif)]">
            {caseData.title}
          </h1>
          <StatusBadge status={caseData.status} />
        </div>
        <div className="flex gap-6 text-sm text-gray-500">
          <span className="font-mono">ID: {caseData.id}</span>
          <span>Level: {caseData.judicial_level}</span>
          <span>
            Created: {new Date(caseData.created_at).toLocaleString()}
          </span>
        </div>
        {status && status.phase !== "pending" && (
          <div className="mt-2 text-sm text-gray-600">
            Phase: <span className="font-medium">{status.phase}</span>
            {" — "}
            {status.message}
          </div>
        )}
      </div>

      {/* Case Progress Pipeline */}
      <CaseProgress
        currentPhase={status?.phase ?? caseData.status}
        escalated={hasEscalation}
        escalationLevel={
          hasEscalation
            ? finalResult.escalation_decisions[
                finalResult.escalation_decisions.length - 1
              ].next_level
            : undefined
        }
      />

      {/* Outcome Summary */}
      {finalResult && (
        <div className="mb-8 rounded-lg border-2 border-emerald-300 bg-gradient-to-r from-emerald-50 to-green-50 p-5 animate-fade-in">
          <h2 className="text-xs font-bold text-emerald-700 mb-3 uppercase tracking-widest">
            Outcome Summary
          </h2>
          <div className="flex flex-wrap items-center gap-8">
            <div>
              <span className="text-xs text-emerald-600 uppercase tracking-wide">
                Predicted Winner
              </span>
              <p className="text-2xl font-bold text-[var(--color-navy-800)] capitalize font-[var(--font-serif)]">
                {finalResult.predicted_winner ?? "Undetermined"}
              </p>
            </div>
            <div>
              <span className="text-xs text-emerald-600 uppercase tracking-wide">
                Confidence
              </span>
              <p className="text-2xl font-bold text-[var(--color-navy-800)]">
                {(finalResult.confidence_estimate * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <span className="text-xs text-emerald-600 uppercase tracking-wide">
                Judicial Stage
              </span>
              <p className="text-2xl font-bold text-[var(--color-navy-800)] font-[var(--font-serif)]">
                {finalResult.judicial_stage}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Facts */}
      <Section title="Case Facts">
        <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed bg-[var(--color-parchment)] rounded-lg p-4 border border-[var(--color-gold-500)]/20">
          {caseData.facts}
        </p>
      </Section>

      {/* Arguments — Courtroom Debate Layout */}
      {iterations.length > 0 && (
        <Section title="Arguments">
          <div className="space-y-6">
            {Array.from(rounds.entries())
              .sort(([a], [b]) => a - b)
              .map(([round, args]) => {
                const claimantArgs = args.filter((a) => a.role === "claimant");
                const respondentArgs = args.filter(
                  (a) => a.role === "respondent",
                );
                return (
                  <div key={round}>
                    <h3 className="text-xs font-bold text-[var(--color-navy-800)] uppercase tracking-widest mb-3">
                      Round {round}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-3 items-start">
                      {/* Claimant side (left, blue) */}
                      <div className="space-y-2">
                        {claimantArgs.map((arg, i) => (
                          <ArgumentCard key={i} arg={arg} side="left" />
                        ))}
                      </div>

                      {/* Center divider with scales icon */}
                      <GavelDivider />

                      {/* Respondent side (right, red) */}
                      <div className="space-y-2">
                        {respondentArgs.map((arg, i) => (
                          <ArgumentCard key={i} arg={arg} side="right" />
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
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

      {/* Court Evaluation — Dramatic Reveal */}
      {courtEval && (
        <Section title="Court Evaluation" className="bg-[var(--color-parchment)]/50 -mx-4 px-4 py-4 rounded-lg">
          <CourtEvalReveal courtEval={courtEval} />
        </Section>
      )}

      {/* MCDA Scores — Animated bars */}
      {mcda && (
        <Section title="MCDA Scoring">
          <AnimatedMCDATable mcda={mcda} />
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
            <div className="rounded-lg border border-[var(--color-navy-800)]/10 p-4 bg-white">
              <h3 className="text-sm font-bold text-[var(--color-navy-800)] uppercase tracking-wider mb-2">
                Precedents
              </h3>
              {finalResult.referenced_precedents.length > 0 ? (
                <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                  {finalResult.referenced_precedents.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-400 italic">No references found</p>
              )}
            </div>
            <div className="rounded-lg border border-[var(--color-navy-800)]/10 p-4 bg-white">
              <h3 className="text-sm font-bold text-[var(--color-navy-800)] uppercase tracking-wider mb-2">
                Laws
              </h3>
              {finalResult.referenced_laws.length > 0 ? (
                <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                  {finalResult.referenced_laws.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-400 italic">No references found</p>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* Full Reasoning Trace */}
      {finalResult && finalResult.full_reasoning_trace.length > 0 && (
        <Section title="Full Reasoning Trace">
          <ol className="list-decimal list-inside text-sm text-gray-700 space-y-2 bg-[var(--color-parchment)] rounded-lg p-5 border border-[var(--color-gold-500)]/20">
            {finalResult.full_reasoning_trace.map((step, i) => (
              <li key={i} className="leading-relaxed animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
                {step}
              </li>
            ))}
          </ol>
        </Section>
      )}
    </div>
  );
}
