import { Link, useLocation } from "react-router-dom";

const links = [
  { to: "/", label: "Cases" },
  { to: "/submit", label: "Submit Case" },
  { to: "/monitor", label: "Monitor" },
];

export default function Nav() {
  const { pathname } = useLocation();
  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="mx-auto max-w-5xl flex items-center gap-6 px-4 h-14">
        <Link to="/" className="text-lg font-bold text-gray-900">
          RalphLex
        </Link>
        {links.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className={`text-sm font-medium ${
              pathname === l.to
                ? "text-blue-600"
                : "text-gray-500 hover:text-gray-900"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
