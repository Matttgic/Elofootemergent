import { Link } from "react-router-dom";
import { Award } from "lucide-react";

// Nom unique du modèle de prévision du site, partout sur le site.
export const MODEL_NAME = "Pronostic FootPulse";

export function ModelTag({ modele, testid }) {
  return (
    <span className="inline-flex items-center rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-300"
      data-testid={testid}>
      Modèle {modele || "Elo"}
    </span>
  );
}

export function BestMethodBadge({ className = "" }) {
  return (
    <Link to="/methodologie#classement" data-testid="best-method-badge"
      className={`inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 hover:bg-emerald-500/20 ${className}`}
      title="La plus précise de nos méthodes sur l'historique : voir le classement des méthodes">
      <Award className="w-3 h-3" /> Meilleure méthode testée
    </Link>
  );
}

// Probabilités 1N2 du pronostic : trois chiffres (le plus probable mis en avant) et la barre.
export function ForecastNumbers({ pred, homeName, awayName, size = "md", testid }) {
  if (!pred) return null;
  const cells = [
    ["domicile", homeName, pred.domicile_pct],
    ["nul", "Nul", pred.nul_pct],
    ["exterieur", awayName, pred.exterieur_pct],
  ];
  const top = cells.reduce((a, b) => (b[2] > a[2] ? b : a))[0];
  const big = size === "lg" ? "text-3xl sm:text-4xl" : "text-2xl";
  return (
    <div data-testid={testid}>
      <div className="grid grid-cols-3 gap-2 text-center">
        {cells.map(([k, label, v]) => (
          <div key={k} className={`rounded-lg py-1.5 ${k === top ? "bg-emerald-500/10 ring-1 ring-emerald-500/40" : ""}`}>
            <div className={`font-stat font-black leading-none ${big} ${k === top ? "text-emerald-300" : "text-slate-300"}`}>
              {Math.round(v)}%
            </div>
            <div className={`mt-1 text-[11px] truncate px-1 ${k === top ? "text-slate-100 font-semibold" : "text-slate-500"}`}>
              {label}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex h-1.5 gap-0.5 overflow-hidden rounded-full">
        <div style={{ width: `${pred.domicile_pct}%` }} className="bg-emerald-500 rounded-l-full" />
        <div style={{ width: `${pred.nul_pct}%` }} className="bg-slate-600" />
        <div style={{ width: `${pred.exterieur_pct}%` }} className="bg-cyan-500 rounded-r-full" />
      </div>
    </div>
  );
}

// Classement des méthodes par indice de précision (0 = simples fréquences, 100 = Pinnacle).
export function MethodRanking({ classement, testid = "method-ranking" }) {
  if (!classement) return null;
  return (
    <div data-testid={testid}>
      <ul className="space-y-2.5">
        {classement.methodes.map((m) => (
          <li key={m.id} data-testid={`${testid}-${m.id}`}
            title={`${m.modele} : log-loss ${m.log_loss.toFixed(4)}, Brier ${m.brier.toFixed(4)}, favori gagnant ${m.reussite_pct} %`}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className={m.site ? "font-semibold text-slate-50" : "text-slate-300"}>
                {m.modele}
                {m.site && <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">sur ce site</span>}
                {m.marche && <span className="ml-2 text-[10px] text-slate-500">bookmaker</span>}
              </span>
              <span className={`font-stat font-bold tabular-nums ${m.site ? "text-slate-50" : "text-slate-400"}`}>{m.indice}</span>
            </div>
            <div className="mt-1 h-2.5 rounded-r bg-slate-800/60">
              <div className={`h-2.5 rounded-r ${m.site ? "bg-emerald-500" : m.marche ? "bg-slate-400" : "bg-slate-600"}`}
                style={{ width: `${Math.max(m.indice, 1)}%` }} />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-slate-500 leading-relaxed">
        Indice de précision : 0 = simples fréquences domicile / nul / extérieur, 100 = cotes Pinnacle à la clôture
        (le marché le plus précis). Mesuré sur les mêmes {classement.matchs.toLocaleString("fr-FR")} matchs
        ({classement.championnats}), chaque saison prédite avec un modèle réglé sur les saisons précédentes.
      </p>
    </div>
  );
}
