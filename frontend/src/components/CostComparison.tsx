import type { CostEstimate } from "../api";

function formatDollars(amount: number): string {
  return "$" + amount.toLocaleString();
}

function formatDuration(months: number): string {
  if (months < 12) return `${months} months`;
  const years = Math.floor(months / 12);
  const rem = months % 12;
  if (rem === 0) return `${years} year${years > 1 ? "s" : ""}`;
  return `${years}y ${rem}m`;
}

function formatProcessingTime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export default function CostComparison({ cost }: { cost: CostEstimate }) {
  const hasEscalation = cost.level_breakdowns.length > 1;

  return (
    <div className="space-y-4">
      {/* Savings banner */}
      <div className="rounded-lg bg-green-50 border border-green-300 p-4 text-center">
        <p className="text-sm text-green-700 font-medium uppercase tracking-wider mb-1">
          Estimated Savings Per Party
        </p>
        <p className="text-2xl font-bold text-green-800 font-[var(--font-serif)]">
          {formatDollars(cost.savings_low)} &ndash; {formatDollars(cost.savings_high)}
        </p>
        <p className="text-xs text-green-600 mt-1">
          Compared to traditional US litigation
        </p>
      </div>

      {/* Side-by-side comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Traditional litigation */}
        <div className="rounded-lg border border-red-200 bg-red-50/50 p-4">
          <h3 className="text-sm font-bold text-red-800 uppercase tracking-wider mb-3 flex items-center gap-2">
            <span className="text-lg">&#9878;</span> Traditional Litigation
          </h3>

          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Attorney Fees (per party)</span>
              <span className="font-medium text-gray-800">
                {formatDollars(cost.total_attorney_fees_per_party_low)} &ndash;{" "}
                {formatDollars(cost.total_attorney_fees_per_party_high)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Court Costs</span>
              <span className="font-medium text-gray-800">
                {formatDollars(cost.total_court_costs_low)} &ndash;{" "}
                {formatDollars(cost.total_court_costs_high)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Expert Witness Fees</span>
              <span className="font-medium text-gray-800">
                {formatDollars(cost.total_expert_fees_low)} &ndash;{" "}
                {formatDollars(cost.total_expert_fees_high)}
              </span>
            </div>
            <hr className="border-red-200" />
            <div className="flex justify-between font-bold">
              <span className="text-gray-700">Total Per Party</span>
              <span className="text-red-800">
                {formatDollars(cost.total_per_party_low)} &ndash;{" "}
                {formatDollars(cost.total_per_party_high)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Estimated Duration</span>
              <span className="font-medium text-gray-800">
                {formatDuration(cost.estimated_duration_months_low)} &ndash;{" "}
                {formatDuration(cost.estimated_duration_months_high)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Complexity</span>
              <span className="font-medium text-gray-800 capitalize">
                {cost.complexity_category} ({cost.argument_rounds} rounds, {cost.complexity_multiplier}x)
              </span>
            </div>
          </div>
        </div>

        {/* RalphLex resolution */}
        <div className="rounded-lg border border-green-200 bg-green-50/50 p-4">
          <h3 className="text-sm font-bold text-green-800 uppercase tracking-wider mb-3 flex items-center gap-2">
            <span className="text-lg">&#9878;</span> RalphLex Resolution
          </h3>

          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Processing Time</span>
              <span className="font-medium text-green-700">
                {formatProcessingTime(cost.ralphlex_processing_seconds)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Cost</span>
              <span className="font-medium text-green-700">
                {cost.ralphlex_cost_estimate}
              </span>
            </div>
            <hr className="border-green-200" />
            <div className="flex justify-between font-bold">
              <span className="text-gray-700">Total Per Party</span>
              <span className="text-green-800">$0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Resolution Time</span>
              <span className="font-medium text-green-700">
                {formatProcessingTime(cost.ralphlex_processing_seconds)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Per-level breakdown for escalated cases */}
      {hasEscalation && (
        <div className="rounded-lg border border-[var(--color-navy-800)]/10 p-4 bg-white">
          <h3 className="text-sm font-bold text-[var(--color-navy-800)] uppercase tracking-wider mb-3">
            Cost Breakdown by Judicial Level (Cumulative)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase">
                  <th className="pb-2 pr-4">Level</th>
                  <th className="pb-2 pr-4">Attorney Fees</th>
                  <th className="pb-2 pr-4">Court Costs</th>
                  <th className="pb-2 pr-4">Expert Fees</th>
                  <th className="pb-2">Duration</th>
                </tr>
              </thead>
              <tbody>
                {cost.level_breakdowns.map((lb, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    <td className="py-2 pr-4 font-medium text-gray-700">
                      {lb.level}
                    </td>
                    <td className="py-2 pr-4 text-gray-600">
                      {formatDollars(lb.attorney_fees_per_party_low)} &ndash;{" "}
                      {formatDollars(lb.attorney_fees_per_party_high)}
                    </td>
                    <td className="py-2 pr-4 text-gray-600">
                      {formatDollars(lb.court_costs_low)} &ndash;{" "}
                      {formatDollars(lb.court_costs_high)}
                    </td>
                    <td className="py-2 pr-4 text-gray-600">
                      {formatDollars(lb.expert_witness_fees_low)} &ndash;{" "}
                      {formatDollars(lb.expert_witness_fees_high)}
                    </td>
                    <td className="py-2 text-gray-600">
                      {formatDuration(lb.duration_months_low)} &ndash;{" "}
                      {formatDuration(lb.duration_months_high)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
