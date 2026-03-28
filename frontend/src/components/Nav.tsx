import { Link, useLocation } from "react-router-dom";

const links = [
  { to: "/", label: "Cases" },
  { to: "/submit", label: "Submit Case" },
  { to: "/monitor", label: "Monitor" },
];

/** Scales of justice SVG icon. */
function ScalesIcon() {
  return (
    <svg
      className="w-6 h-6 text-[var(--color-gold-500)]"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {/* Center pillar */}
      <line x1="12" y1="3" x2="12" y2="21" />
      {/* Base */}
      <line x1="8" y1="21" x2="16" y2="21" />
      {/* Beam */}
      <line x1="4" y1="7" x2="20" y2="7" />
      {/* Left pan */}
      <path d="M4 7l-1 6h6l-1-6" />
      <path d="M3 13a3 3 0 006 0" />
      {/* Right pan */}
      <path d="M20 7l-1 6h6l-1-6" transform="translate(-4,0)" />
      <path d="M15 13a3 3 0 006 0" />
    </svg>
  );
}

export default function Nav() {
  const { pathname } = useLocation();
  return (
    <nav className="bg-[var(--color-navy-900)] border-b border-[var(--color-gold-500)]/30">
      <div className="mx-auto max-w-6xl flex items-center gap-6 px-4 h-14">
        <Link to="/" className="flex items-center gap-2 group">
          <ScalesIcon />
          <span className="text-lg font-bold font-[var(--font-serif)] text-white tracking-wide group-hover:text-[var(--color-gold-400)] transition-colors">
            RalphLex
          </span>
        </Link>
        <div className="flex items-center gap-1 ml-4">
          {links.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                pathname === l.to
                  ? "text-[var(--color-gold-400)] bg-white/10"
                  : "text-gray-300 hover:text-white hover:bg-white/5"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
