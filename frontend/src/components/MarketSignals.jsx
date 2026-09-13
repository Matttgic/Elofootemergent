import { statutColor } from "../lib/format";
import { TrendingUp, AlertTriangle } from "lucide-react";

function SignalCard({ s }) {
  const color = statutColor(s.statut);
  return (
    <div className="card-surface rounded-xl p-4" data-testid={`market-signal-${s.marche.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="font-semibold text-sm text-slate-100">{s.marche}</div>
        <span className="text-[11px] font-stat font-bold px-2 py-0.5 rounded shrink-0"
              style={{ color, backgroundColor: `${color}1A`, border: `1px solid ${color}44` }}>
          {s.statut}
        </span>
      </div>
      <div className="flex items-center gap-3 mb-2">
        <span className="text-lg font-black font-stat" style={{ color }}>{s.valeur}</span>
        <span className="text-xs text-slate-500">Confiance statistique : <b className="text-slate-300">{s.confiance}</b></span>
      </div>
      <p className="text-xs text-slate-400 leading-relaxed">{s.explication}</p>
    </div>
  );
}

export function MarketSignals({ data }) {
  if (!data || !data.disponible) {
    return (
      <div className="card-surface rounded-xl p-4 text-sm text-slate-400">
        {data?.message || "Signaux indisponibles."}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
        <AlertTriangle className="w-4 h-4 shrink-0" />
        <span className="text-xs">{data.avertissement}</span>
      </div>
      {data.buts_estimes && (
        <div className="flex items-center gap-2 text-xs text-slate-400 font-stat">
          <TrendingUp className="w-4 h-4 text-emerald-400" />
          Total de buts estimé : <b className="text-slate-100">{data.buts_estimes.total}</b>
          (dom. {data.buts_estimes.domicile} / ext. {data.buts_estimes.exterieur})
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {data.signaux.map((s, i) => <SignalCard key={i} s={s} />)}
      </div>
    </div>
  );
}
