import { Zap } from "lucide-react";

const ISSUE_LABEL = { domicile: "Victoire dom.", nul: "Nul", exterieur: "Victoire ext." };

// Barre 1N2 du modèle Elo : domicile (vert), nul (gris), extérieur (cyan).
export function ProbabilityBar({ pred, homeName, awayName, testid }) {
  if (!pred) return null;
  return (
    <div data-testid={testid}>
      <div className="flex h-2 rounded-full overflow-hidden bg-slate-900">
        <div style={{ width: `${pred.domicile_pct}%` }} className="bg-emerald-500 transition-[width] duration-500" />
        <div style={{ width: `${pred.nul_pct}%` }} className="bg-slate-600 transition-[width] duration-500" />
        <div style={{ width: `${pred.exterieur_pct}%` }} className="bg-cyan-500 transition-[width] duration-500" />
      </div>
      <div className="flex items-center justify-between mt-1 text-[10px] font-stat gap-2">
        <span className="text-emerald-400 truncate">{homeName} {Math.round(pred.domicile_pct)}%</span>
        <span className="text-slate-500 shrink-0">Nul {Math.round(pred.nul_pct)}%</span>
        <span className="text-cyan-400 truncate text-right">{awayName} {Math.round(pred.exterieur_pct)}%</span>
      </div>
    </div>
  );
}

// Cotes figées du bookmaker, avec l'issue « value » mise en évidence.
export function OddsLine({ cotes, value, testid }) {
  if (!cotes) return null;
  const cell = (key, label) => (
    <span className={`font-stat tabular-nums ${value?.issue === key ? "text-amber-400 font-bold" : "text-slate-300"}`}>
      {label} {cotes[key]?.toFixed ? cotes[key].toFixed(2) : "—"}
    </span>
  );
  return (
    <div className="flex items-center justify-between gap-2 text-[10px] text-slate-500" data-testid={testid}>
      <span className="uppercase tracking-wide">Cotes</span>
      <span className="flex items-center gap-2.5">{cell("domicile", "1")}{cell("nul", "N")}{cell("exterieur", "2")}</span>
    </div>
  );
}

export function ValueBadge({ value, testid }) {
  if (!value) return null;
  return (
    <span className="inline-flex items-center gap-0.5 text-amber-400 font-bold" data-testid={testid}
      title={`${ISSUE_LABEL[value.issue]} : ${value.proba_pct}% selon le modèle, cote ${value.cote} → avantage théorique ${value.avantage_pct}%. `
        + "Historiquement, ces écarts entre modèle et bookmaker n'ont pas été rentables."}>
      <Zap className="w-3 h-3 fill-amber-400" /> VALUE
    </span>
  );
}
