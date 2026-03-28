/** Color-coded status badge for case status. */

const statusStyles: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  escalated: "bg-orange-100 text-orange-700",
};

export default function StatusBadge({ status }: { status: string }) {
  const style = statusStyles[status] ?? "bg-gray-100 text-gray-700";
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}
    >
      {status}
    </span>
  );
}
