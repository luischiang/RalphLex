/**
 * CaseProgress — visual pipeline/stepper showing the Ralph Loop phases.
 * Phases: Case Filed -> Arguments -> Legal Research -> Court Evaluation -> MCDA Scoring -> Escalation Check -> Resolved
 * Active phase pulses, completed phases show checkmark, future phases are grayed.
 * If escalation occurred, shows a branch looping back to Arguments.
 */

const PHASES = [
  { key: "filed", label: "Case Filed" },
  { key: "arguing", label: "Arguments" },
  { key: "retrieving_references", label: "Legal Research" },
  { key: "evaluating", label: "Court Evaluation" },
  { key: "scoring", label: "MCDA Scoring" },
  { key: "checking_escalation", label: "Escalation Check" },
  { key: "resolved", label: "Resolved" },
] as const;

/** Map backend phase names to our pipeline keys. */
function mapPhase(backendPhase: string): string {
  const mapping: Record<string, string> = {
    pending: "filed",
    started: "filed",
    arguing: "arguing",
    retrieving_references: "retrieving_references",
    evaluating: "evaluating",
    checking_escalation: "checking_escalation",
    escalating: "checking_escalation",
    scoring: "scoring",
    refining: "scoring",
    completed: "resolved",
    failed: "resolved",
  };
  return mapping[backendPhase] ?? "filed";
}

function getPhaseIndex(phase: string): number {
  const mapped = mapPhase(phase);
  const idx = PHASES.findIndex((p) => p.key === mapped);
  return idx >= 0 ? idx : 0;
}

interface CaseProgressProps {
  currentPhase: string;
  escalated?: boolean;
  escalationLevel?: string;
}

export default function CaseProgress({
  currentPhase,
  escalated,
  escalationLevel,
}: CaseProgressProps) {
  const activeIdx = getPhaseIndex(currentPhase);
  const isComplete = currentPhase === "completed";

  return (
    <div className="mb-6">
      {/* Pipeline */}
      <div className="flex items-center justify-between overflow-x-auto gap-1">
        {PHASES.map((phase, i) => {
          const isActive = i === activeIdx && !isComplete;
          const isDone = isComplete || i < activeIdx;
          const isFuture = !isDone && !isActive;

          return (
            <div key={phase.key} className="flex items-center flex-1 min-w-0">
              {/* Node */}
              <div className="flex flex-col items-center flex-shrink-0">
                <div
                  className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                    isDone
                      ? "bg-[var(--color-navy-800)] border-[var(--color-gold-500)] text-[var(--color-gold-400)]"
                      : isActive
                        ? "bg-[var(--color-gold-500)] border-[var(--color-gold-400)] text-[var(--color-navy-900)] animate-phase-pulse"
                        : "bg-gray-200 border-gray-300 text-gray-400"
                  }`}
                >
                  {isDone ? (
                    <span className="animate-check-slide">&#10003;</span>
                  ) : (
                    i + 1
                  )}
                </div>
                <span
                  className={`mt-1.5 text-[10px] font-medium text-center leading-tight whitespace-nowrap ${
                    isDone
                      ? "text-[var(--color-navy-800)]"
                      : isActive
                        ? "text-[var(--color-gold-500)] font-semibold"
                        : "text-gray-400"
                  }`}
                >
                  {phase.label}
                </span>
              </div>

              {/* Connector line */}
              {i < PHASES.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-1 mt-[-18px] ${
                    i < activeIdx || isComplete
                      ? "bg-[var(--color-gold-500)]"
                      : isFuture
                        ? "bg-gray-200"
                        : "bg-[var(--color-gold-300)]"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Escalation badge */}
      {escalated && (
        <div className="mt-3 flex items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 border border-amber-300 px-3 py-1 text-amber-800 font-medium">
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 11l3-3m0 0l3 3m-3-3v8m0-13a9 9 0 110 18 9 9 0 010-18z"
              />
            </svg>
            Escalated{escalationLevel ? ` to ${escalationLevel}` : ""} — loop
            restarted at Arguments
          </span>
        </div>
      )}
    </div>
  );
}
