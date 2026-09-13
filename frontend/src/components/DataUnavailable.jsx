import { Badge } from "../components/ui/badge";

export function DataUnavailable({ label = "Donnée indisponible", className = "" }) {
  return (
    <Badge
      data-testid="data-unavailable-badge"
      className={`bg-slate-800 text-slate-400 border border-slate-700 text-xs px-2 py-0.5 rounded font-stat font-medium hover:bg-slate-800 ${className}`}
    >
      {label}
    </Badge>
  );
}
