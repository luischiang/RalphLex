import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type {
  CaseListItem,
  MCDAResult,
  StatusResponse,
  TimelineEntry,
} from "../api";
import {
  getCaseStatus,
  getCaseTimeline,
  getOutput,
  listCases,
  runSampleCase,
} from "../api";
import CaseProgress from "../components/CaseProgress";
import StatusBadge from "../components/StatusBadge";

/* ===== Helpers ===== */

interface StatusCounts {
  pending: number;
  running: number;
  completed: number;
  escalated: number;
}

function countByStatus(cases: CaseListItem[]): StatusCounts {
  const counts: StatusCounts = { pending: 0, running: 0, completed: 0, escalated: 0 };
  for (const c of cases) {
    if (c.status in counts) {
      counts[c.status as keyof StatusCounts]++;
    }
  }
  return counts;
}

/** Phase display labels. */
const phaseLabels: Record<string, string> = {
  started: "Starting",
  arguing: "Arguing",
  retrieving_references: "Retrieving References",
  evaluating: "Evaluating",
  checking_escalation: "Checking Escalation",
  escalating: "Escalating",
  completed: "Completed",
  failed: "Failed",
  pending: "Pending",
  refining: "Refining",
};

/* ===== Typewriter Hook ===== */

function useTypewriter(text: string, speed: number = 30): string {
  const [displayed, setDisplayed] = useState("");
  const prevText = useRef(text);

  useEffect(() => {
    // Only animate when text changes
    if (text === prevText.current && displayed === text) return;
    prevText.current = text;
    setDisplayed("");
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(interval);
    }, speed);
    return () => clearInterval(interval);
  }, [text, speed, displayed]);

  return displayed || text;
}

/* ===== Real-time Elapsed Counter ===== */

function ElapsedCounter({ startDate }: { startDate: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const diff = now - new Date(startDate).getTime();
  if (diff < 0) return <span>just now</span>;
  const secs = Math.floor(diff / 1000);
  const mins = Math.floor(secs / 60);
  const hrs = Math.floor(mins / 60);
  let str: string;
  if (hrs > 0) str = `${hrs}h ${mins % 60}m ${secs % 60}s`;
  else if (mins > 0) str = `${mins}m ${secs % 60}s`;
  else str = `${secs}s`;

  return <span className="font-mono tabular-nums">{str}</span>;
}

/* ===== Summary Bar ===== */

function SummaryBar({ counts }: { counts: StatusCounts }) {
  const items: { label: string; count: number; color: string; border: string }[] = [
    { label: "Pending", count: counts.pending, color: "bg-gray-50 text-gray-700", border: "border-gray-200" },
    { label: "Running", count: counts.running, color: "bg-blue-50 text-blue-800", border: "border-blue-200" },
    { label: "Completed", count: counts.completed, color: "bg-emerald-50 text-emerald-800", border: "border-emerald-200" },
    { label: "Escalated", count: counts.escalated, color: "bg-amber-50 text-amber-800", border: "border-amber-200" },
  ];
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-lg border-2 p-4 text-center ${item.color} ${item.border}`}
        >
          <div className="text-3xl font-bold font-[var(--font-serif)]">
            {item.count}
          </div>
          <div className="text-xs font-semibold uppercase tracking-wider mt-1">
            {item.label}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ===== Timeline View ===== */

function TimelineView({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-xs text-gray-400 italic">No timeline events yet.</p>;
  }
  return (
    <div className="relative ml-4 border-l-2 border-[var(--color-navy-800)]/20 pl-4 space-y-3">
      {entries.map((entry, i) => (
        <div
          key={i}
          className={`relative ${entry.is_escalation ? "border-l-2 border-amber-400 -ml-[18px] pl-4" : ""}`}
        >
          <div
            className={`absolute -left-[25px] top-1 w-3 h-3 rounded-full border-2 border-white ${
              entry.is_escalation
                ? "bg-amber-500"
                : entry.phase === "completed"
                  ? "bg-emerald-500"
                  : entry.phase === "arguing"
                    ? "bg-blue-500"
                    : entry.phase === "evaluating"
                      ? "bg-purple-500"
                      : "bg-gray-400"
            }`}
          />
          <div
            className={`rounded p-2 text-xs ${
              entry.is_escalation
                ? "bg-amber-50 border border-amber-200"
                : "bg-gray-50 border border-gray-100"
            }`}
          >
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-semibold text-[var(--color-navy-800)]">
                {entry.event}
              </span>
              <span className="text-gray-400">
                {new Date(entry.timestamp).toLocaleTimeString()}
              </span>
            </div>
            {entry.details.content_preview && (
              <p className="text-gray-500 truncate max-w-md">
                {String(entry.details.content_preview)}
              </p>
            )}
            {entry.phase === "completed" && entry.details.predicted_winner && (
              <p className="text-gray-600">
                Winner:{" "}
                <span className="font-semibold">
                  {String(entry.details.predicted_winner)}
                </span>
                {entry.details.confidence_estimate != null && (
                  <span className="ml-2">
                    ({(Number(entry.details.confidence_estimate) * 100).toFixed(1)}%
                    confidence)
                  </span>
                )}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ===== MCDA Progression ===== */

function MCDAProgression({ results }: { results: MCDAResult[] }) {
  if (results.length === 0) return null;
  return (
    <div className="mt-3">
      <h4 className="text-xs font-bold text-[var(--color-navy-800)] uppercase tracking-wider mb-2">
        MCDA Score Progression
      </h4>
      <div className="overflow-hidden rounded-lg border border-[var(--color-navy-800)]/20">
        <table className="min-w-full divide-y divide-gray-200 text-xs">
          <thead className="bg-[var(--color-navy-900)]">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium text-[var(--color-gold-400)] uppercase">
                Level
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-blue-300 uppercase">
                Claimant
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-red-300 uppercase">
                Respondent
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-[var(--color-gold-400)] uppercase">
                Winner
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-[var(--color-gold-400)] uppercase">
                Confidence
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {results.map((m, i) => (
              <tr key={i}>
                <td className="px-3 py-1.5 text-gray-700 font-medium">
                  Level {i + 1}
                </td>
                <td className="px-3 py-1.5 text-right font-mono text-blue-700">
                  {m.weighted_totals.claimant?.toFixed(3) ?? "-"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono text-red-700">
                  {m.weighted_totals.respondent?.toFixed(3) ?? "-"}
                </td>
                <td className="px-3 py-1.5 text-right font-semibold">
                  {m.predicted_winner ?? "-"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {(m.confidence * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ===== Active Case Card ===== */

interface ActiveCaseInfo {
  caseItem: CaseListItem;
  status: StatusResponse | null;
  timeline: TimelineEntry[];
  mcdaResults: MCDAResult[];
  expanded: boolean;
}

function ActiveCaseCard({
  info,
  onToggle,
}: {
  info: ActiveCaseInfo;
  onToggle: () => void;
}) {
  const { caseItem, status, timeline, mcdaResults, expanded } = info;
  const iteration = timeline.filter((e) => e.phase === "arguing").length;
  const phase = status?.phase ?? "pending";
  const isRunning = caseItem.status === "running" || caseItem.status === "escalated";

  // Typewriter status message
  const statusText = `${phaseLabels[phase] ?? phase}${
    status?.message ? ` — ${status.message}` : ""
  }`;
  const typewriterText = useTypewriter(
    isRunning ? statusText : phaseLabels[phase] ?? phase,
    25,
  );

  return (
    <div
      className={`rounded-lg border-2 bg-white overflow-hidden transition-colors ${
        isRunning
          ? "border-[var(--color-navy-800)]/20"
          : "border-gray-200"
      }`}
    >
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-gray-50 transition-colors"
      >
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to={`/cases/${caseItem.id}`}
              className="text-sm font-semibold text-[var(--color-navy-800)] hover:text-[var(--color-gold-500)] truncate transition-colors"
              onClick={(e) => e.stopPropagation()}
            >
              {caseItem.title}
            </Link>
            <StatusBadge status={caseItem.status} />
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500 mt-0.5">
            {/* Pulsing dot for active phase */}
            {isRunning && (
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[var(--color-gold-500)] animate-pulse-dot" />
                <span className="text-[var(--color-navy-800)] font-medium">
                  {typewriterText}
                </span>
              </span>
            )}
            {!isRunning && (
              <span>
                Phase:{" "}
                <span className="font-medium text-gray-700">
                  {phaseLabels[phase] ?? phase}
                </span>
              </span>
            )}
            <span>
              Iteration:{" "}
              <span className="font-medium text-gray-700">
                {Math.ceil(iteration / 2)}
              </span>
            </span>
            <span>
              Elapsed:{" "}
              {isRunning ? (
                <ElapsedCounter startDate={caseItem.created_at} />
              ) : (
                <span className="font-mono">
                  {elapsedStatic(caseItem.created_at)}
                </span>
              )}
            </span>
          </div>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100 animate-fade-in">
          {/* CaseProgress for running cases */}
          {isRunning && status && (
            <div className="mt-3">
              <CaseProgress currentPhase={status.phase} />
            </div>
          )}

          <div className="mt-3">
            <h4 className="text-xs font-bold text-[var(--color-navy-800)] uppercase tracking-wider mb-2">
              Timeline
            </h4>
            <TimelineView entries={timeline} />
          </div>
          <MCDAProgression results={mcdaResults} />
        </div>
      )}
    </div>
  );
}

/** Static elapsed (for non-running cases). */
function elapsedStatic(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 0) return "just now";
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

/* ===== Main Monitor Component ===== */

export default function Monitor() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [activeInfos, setActiveInfos] = useState<Map<string, ActiveCaseInfo>>(
    new Map(),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sampleRunning, setSampleRunning] = useState(false);
  const [sampleTemplate, setSampleTemplate] = useState("contract");
  const expandedRef = useRef<Set<string>>(new Set());

  const handleRunSample = async () => {
    setSampleRunning(true);
    try {
      await runSampleCase(sampleTemplate);
      await fetchAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSampleRunning(false);
    }
  };

  const fetchAll = useCallback(async () => {
    try {
      const allCases = await listCases();
      setCases(allCases);

      const activeCases = allCases.filter(
        (c) => c.status === "running" || c.status === "escalated",
      );

      const infos = new Map<string, ActiveCaseInfo>();
      await Promise.all(
        allCases.map(async (caseItem) => {
          const isActive = activeCases.some((a) => a.id === caseItem.id);
          try {
            const [statusRes, timeline] = await Promise.all([
              isActive ? getCaseStatus(caseItem.id) : Promise.resolve(null),
              getCaseTimeline(caseItem.id),
            ]);

            const mcdaResults: MCDAResult[] = [];
            const currentMcda = await getOutput<MCDAResult>(
              caseItem.id,
              "mcda_scoring.json",
            );
            if (currentMcda) {
              mcdaResults.push(currentMcda);
            }

            infos.set(caseItem.id, {
              caseItem,
              status: statusRes,
              timeline,
              mcdaResults,
              expanded: expandedRef.current.has(caseItem.id),
            });
          } catch {
            infos.set(caseItem.id, {
              caseItem,
              status: null,
              timeline: [],
              mcdaResults: [],
              expanded: expandedRef.current.has(caseItem.id),
            });
          }
        }),
      );

      setActiveInfos(infos);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAll();
    const interval = setInterval(() => void fetchAll(), 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const toggleExpand = (caseId: string) => {
    setActiveInfos((prev) => {
      const next = new Map(prev);
      const info = next.get(caseId);
      if (info) {
        const newExpanded = !info.expanded;
        next.set(caseId, { ...info, expanded: newExpanded });
        if (newExpanded) {
          expandedRef.current.add(caseId);
        } else {
          expandedRef.current.delete(caseId);
        }
      }
      return next;
    });
  };

  if (loading)
    return <p className="p-6 text-gray-500">Loading monitor...</p>;
  if (error) return <p className="p-6 text-red-600">{error}</p>;

  const counts = countByStatus(cases);
  const activeCases = cases.filter(
    (c) => c.status === "running" || c.status === "escalated",
  );
  const otherCases = cases.filter(
    (c) => c.status !== "running" && c.status !== "escalated",
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-[var(--color-navy-800)] font-[var(--font-serif)]">
          Monitoring Dashboard
        </h1>
        <div className="flex items-center gap-2">
          <select
            value={sampleTemplate}
            onChange={(e) => setSampleTemplate(e.target.value)}
            className="rounded-md border-2 border-[var(--color-navy-800)]/20 px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-[var(--color-gold-500)] focus:border-[var(--color-gold-500)]"
          >
            <option value="contract">Contract Dispute</option>
            <option value="employment">Employment Termination</option>
            <option value="property">Property Damage</option>
            <option value="first_amendment">
              First Amendment (Constitutional)
            </option>
            <option value="due_process">Due Process (Regulatory Taking)</option>
            <option value="antitrust">Antitrust (Federal/Interstate)</option>
          </select>
          <button
            onClick={() => void handleRunSample()}
            disabled={sampleRunning}
            className="rounded-md bg-[var(--color-navy-800)] px-4 py-1.5 text-sm font-medium text-[var(--color-gold-400)] hover:bg-[var(--color-navy-700)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {sampleRunning ? "Starting..." : "Run Sample Case"}
          </button>
        </div>
      </div>

      <SummaryBar counts={counts} />

      {/* Active cases */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-[var(--color-navy-800)] font-[var(--font-serif)] mb-3">
          Active Cases
          {activeCases.length > 0 && (
            <span className="ml-2 text-sm font-normal text-gray-400">
              (updates every 5s)
            </span>
          )}
        </h2>
        {activeCases.length === 0 ? (
          <p className="text-sm text-gray-500">No active cases.</p>
        ) : (
          <div className="space-y-3">
            {activeCases.map((c) => {
              const info = activeInfos.get(c.id);
              if (!info) return null;
              return (
                <ActiveCaseCard
                  key={c.id}
                  info={info}
                  onToggle={() => toggleExpand(c.id)}
                />
              );
            })}
          </div>
        )}
      </section>

      {/* Other cases */}
      {otherCases.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-[var(--color-navy-800)] font-[var(--font-serif)] mb-3">
            Other Cases
          </h2>
          <div className="space-y-3">
            {otherCases.map((c) => {
              const info = activeInfos.get(c.id);
              if (!info) return null;
              return (
                <ActiveCaseCard
                  key={c.id}
                  info={info}
                  onToggle={() => toggleExpand(c.id)}
                />
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
