import { Zap } from "lucide-react";

const ISSUE_LABEL = { domicile: "Victoire dom.", nul: "Nul", exterieur: "Victoire ext." };

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
