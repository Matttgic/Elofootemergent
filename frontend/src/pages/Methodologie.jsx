import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui/skeleton";
import { BookOpen, ShieldCheck, Scale } from "lucide-react";

function WeightBlock({ title, weights }) {
  const entries = Object.entries(weights || {});
  return (
    <div className="card-surface rounded-xl p-5">
      <h3 className="font-head font-bold text-slate-100 mb-3">{title}</h3>
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-slate-300 capitalize">{k.replace(/_/g, " ")}</span>
              <span className="font-stat font-bold text-emerald-400 text-sm">{Math.round(v * 100)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${v * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Methodologie() {
  const [c, setC] = useState(null);
  useEffect(() => { api.get("/scoring/config").then((r) => setC(r.data)).catch(() => {}); }, []);

  if (!c) return <div className="max-w-3xl mx-auto px-4 py-6 space-y-4"><Skeleton className="h-32 rounded-xl bg-slate-800/50" /></div>;

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1 flex items-center gap-2">
        <BookOpen className="w-7 h-7 text-emerald-400" /> Méthodologie
      </h1>
      <p className="text-slate-400 text-sm mb-6">Coefficients et principes de calcul — transparents et reproductibles.</p>

      <div className="space-y-4">
        <div className="card-surface rounded-xl p-5">
          <div className="flex items-start gap-3">
            <Scale className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <p className="text-sm text-slate-300 leading-relaxed">{c.principe}</p>
          </div>
        </div>
        <div className="card-surface rounded-xl p-5 border-emerald-500/20 bg-emerald-500/5">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-emerald-300 text-sm mb-1">Protection anti-biais</div>
              <p className="text-sm text-slate-300 leading-relaxed">{c.anti_biais}</p>
            </div>
          </div>
        </div>

        <WeightBlock title="Score global — pondération" weights={c.score_global} />
        <WeightBlock title="Score offensif — pondération" weights={c.score_offensif} />
        <WeightBlock title="Score défensif — pondération" weights={c.score_defensif} />

        <div className="card-surface rounded-xl p-5">
          <h3 className="font-head font-bold text-slate-100 mb-2">Données indisponibles avec la source gratuite</h3>
          <div className="flex flex-wrap gap-2 mb-3">
            {(c.donnees_indisponibles || []).map((d) => (
              <span key={d} className="text-xs bg-slate-800 text-slate-400 border border-slate-700 rounded px-2 py-0.5 font-stat">{d}</span>
            ))}
          </div>
          <p className="text-xs text-slate-500">{c.note_donnees}</p>
        </div>
      </div>
    </div>
  );
}
