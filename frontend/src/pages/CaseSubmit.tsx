import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createCase } from "../api";

export default function CaseSubmit() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [facts, setFacts] = useState("");
  const [partyRole, setPartyRole] = useState<"claimant" | "respondent">(
    "claimant",
  );
  const [materials, setMaterials] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await createCase({
        title,
        facts,
        party_role: partyRole,
        supporting_materials: materials || undefined,
      });
      navigate(`/cases/${res.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Submit a Case
      </h1>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Case Title
          </label>
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            placeholder="e.g., Contract Breach - Acme vs Beta Corp"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Facts
          </label>
          <textarea
            required
            rows={6}
            value={facts}
            onChange={(e) => setFacts(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            placeholder="Describe the case facts..."
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Party Role
          </label>
          <select
            value={partyRole}
            onChange={(e) =>
              setPartyRole(e.target.value as "claimant" | "respondent")
            }
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
          >
            <option value="claimant">Claimant</option>
            <option value="respondent">Respondent</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Supporting Materials
          </label>
          <textarea
            rows={4}
            value={materials}
            onChange={(e) => setMaterials(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            placeholder="Optional: documents, evidence, or additional context..."
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Submitting..." : "Submit Case"}
        </button>
      </form>
    </div>
  );
}
