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
} from "../api";
import StatusBadge from "../components/StatusBadge";

/** Summary counts by status. */
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

/** Format elapsed time from a date string to now. */
function elapsed(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 0) return "just now";
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
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
};

function SummaryBar({ counts }: { counts: StatusCounts }) {
  const items: { label: string; count: number; color: string }[] = [
    { label: "Pending", count: counts.pending, color: "bg-gray-100 text-gray-700" },
    { label: "Running", count: counts.running, color: "bg-blue-100 text-blue-700" },
    { label: "Completed", count: counts.completed, color: "bg-green-100 text-green-700" },
    { label: "Escalated", count: counts.escalated, color: "bg-orange-100 text-orange-700" },
  ];
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-lg p-4 text-center ${item.color}`}
        >
          <div className="text-2xl font-bold">{item.count}</div>
          <div className="text-xs font-medium uppercase">{item.label}</div>
        </div>
      ))}
    </div>
  );
}

interface ActiveCaseInfo {
  caseItem: CaseListItem;
  status: StatusResponse | null;
  timeline: TimelineEntry[];
  mcdaResults: MCDAResult[];
  expanded: boolean;
}

function TimelineView({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-xs text-gray-400 italic">No timeline events yet.</p>;
  }
  return (
    <div className="relative ml-4 border-l-2 border-gray-200 pl-4 space-y-3">
      {entries.map((entry, i) => (
        <div
          key={i}
          className={`relative ${entry.is_escalation ? "border-l-2 border-orange-400 -ml-[18px] pl-4" : ""}`}
        >
          {/* Dot */}
          <div
            className={`absolute -left-[25px] top-1 w-3 h-3 rounded-full border-2 border-white ${
              entry.is_escalation
                ? "bg-orange-500"
                : entry.phase === "completed"
                  ? "bg-green-500"
                  : entry.phase === "arguing"
                    ? "bg-blue-400"
                    : entry.phase === "evaluating"
                      ? "bg-purple-400"
                      : "bg-gray-400"
            }`}
          />
          <div
            className={`rounded p-2 text-xs ${
              entry.is_escalation
                ? "bg-orange-50 border border-orange-200"
                : "bg-gray-50"
            }`}
          >
            <div className="flex items-center gap-2 mb-0.5">
              <span className="font-medium text-gray-800">{entry.event}</span>
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
                Winner: <span className="font-medium">{String(entry.details.predicted_winner)}</span>
                {entry.details.confidence_estimate != null && (
                  <span className="ml-2">
                    ({(Number(entry.details.confidence_estimate) * 100).toFixed(1)}% confidence)
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

function MCDAProgression({ results }: { results: MCDAResult[] }) {
  if (results.length === 0) return null;
  return (
    <div className="mt-3">
      <h4 className="text-xs font-medium text-gray-600 mb-2">
        MCDA Score Progression
      </h4>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-xs">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-1.5 text-left font-medium text-gray-500 uppercase">
                Level
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-gray-500 uppercase">
                Claimant
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-gray-500 uppercase">
                Respondent
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-gray-500 uppercase">
                Winner
              </th>
              <th className="px-3 py-1.5 text-right font-medium text-gray-500 uppercase">
                Confidence
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {results.map((m, i) => (
              <tr key={i}>
                <td className="px-3 py-1.5 text-gray-700">Level {i + 1}</td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {m.weighted_totals.claimant?.toFixed(3) ?? "-"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {m.weighted_totals.respondent?.toFixed(3) ?? "-"}
                </td>
                <td className="px-3 py-1.5 text-right font-medium">
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

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={onToggle}
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-gray-50"
      >
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to={`/cases/${caseItem.id}`}
              className="text-sm font-medium text-blue-600 hover:underline truncate"
              onClick={(e) => e.stopPropagation()}
            >
              {caseItem.title}
            </Link>
            <StatusBadge status={caseItem.status} />
          </div>
          <div className="flex gap-4 text-xs text-gray-500 mt-0.5">
            <span>
              Phase: <span className="font-medium text-gray-700">{phaseLabels[phase] ?? phase}</span>
            </span>
            <span>
              Iteration: <span className="font-medium text-gray-700">{Math.ceil(iteration / 2)}</span>
            </span>
            <span>Elapsed: {elapsed(caseItem.created_at)}</span>
          </div>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100">
          <div className="mt-3">
            <h4 className="text-xs font-medium text-gray-600 mb-2">Timeline</h4>
            <TimelineView entries={timeline} />
          </div>
          <MCDAProgression results={mcdaResults} />
        </div>
      )}
    </div>
  );
}

export default function Monitor() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [activeInfos, setActiveInfos] = useState<Map<string, ActiveCaseInfo>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const expandedRef = useRef<Set<string>>(new Set());

  const fetchAll = useCallback(async () => {
    try {
      const allCases = await listCases();
      setCases(allCases);

      // Fetch details for active (running/escalated) + recently completed cases
      const activeCases = allCases.filter(
        (c) => c.status === "running" || c.status === "escalated",
      );
      // Also include completed/pending for timeline viewing
      const allForTimeline = allCases;

      const infos = new Map<string, ActiveCaseInfo>();
      await Promise.all(
        allForTimeline.map(async (caseItem) => {
          const isActive = activeCases.some((a) => a.id === caseItem.id);
          try {
            const [statusRes, timeline] = await Promise.all([
              isActive ? getCaseStatus(caseItem.id) : Promise.resolve(null),
              getCaseTimeline(caseItem.id),
            ]);

            // Collect MCDA results from archived levels and current
            const mcdaResults: MCDAResult[] = [];
            // Check for archived level MCDA files via timeline escalation events
            const currentMcda = await getOutput<MCDAResult>(caseItem.id, "mcda_scoring.json");
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

  if (loading) return <p className="p-6 text-gray-500">Loading monitor...</p>;
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
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Monitoring Dashboard
      </h1>

      {/* Summary bar */}
      <SummaryBar counts={counts} />

      {/* Active cases */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">
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
          <h2 className="text-lg font-semibold text-gray-900 mb-3">
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
