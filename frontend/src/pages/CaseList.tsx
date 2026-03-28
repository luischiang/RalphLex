import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { CaseListItem } from "../api";
import { listCases } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function CaseList() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCases()
      .then(setCases)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return <p className="p-6 text-gray-500">Loading cases...</p>;
  if (error) return <p className="p-6 text-red-600">{error}</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-[var(--color-navy-800)] font-[var(--font-serif)]">
          Cases
        </h1>
        <Link
          to="/submit"
          className="rounded-md bg-[var(--color-navy-800)] px-4 py-2 text-sm font-medium text-[var(--color-gold-400)] hover:bg-[var(--color-navy-700)] transition-colors"
        >
          Submit Case
        </Link>
      </div>

      {cases.length === 0 ? (
        <p className="text-gray-500">No cases yet.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border-2 border-[var(--color-navy-800)]/10">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-[var(--color-navy-900)]">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-gold-400)] uppercase tracking-wider">
                  ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-gold-400)] uppercase tracking-wider">
                  Title
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-gold-400)] uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-gold-400)] uppercase tracking-wider">
                  Judicial Level
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-gold-400)] uppercase tracking-wider">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {cases.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <Link
                      to={`/cases/${c.id}`}
                      className="text-[var(--color-navy-800)] hover:text-[var(--color-gold-500)] font-mono transition-colors"
                    >
                      {c.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    <Link
                      to={`/cases/${c.id}`}
                      className="hover:text-[var(--color-gold-500)] transition-colors"
                    >
                      {c.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {c.judicial_level}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {new Date(c.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
