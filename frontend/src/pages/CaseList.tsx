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
        <h1 className="text-2xl font-bold text-gray-900">Cases</h1>
        <Link
          to="/submit"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Submit Case
        </Link>
      </div>

      {cases.length === 0 ? (
        <p className="text-gray-500">No cases yet.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Title
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Judicial Level
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {cases.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm">
                    <Link
                      to={`/cases/${c.id}`}
                      className="text-blue-600 hover:underline font-mono"
                    >
                      {c.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    <Link
                      to={`/cases/${c.id}`}
                      className="hover:underline"
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
