import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui/skeleton";
import { PieChart, TrendingUp, Home as HomeIcon, Scale } from "lucide-react";

function TriBar({ a, b, c, labels }) {
  const av = a ?? 0, bv = b ?? 0, cv = c ?? 0;
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden bg-slate-800">
        <div style={{ width: `${av}%`, backgroundColor: "#10B981" }} />
        <div style={{ width: `${bv}%`, backgroundColor: "#64748B" }} />
        <div style={{ width: `${cv}%`, backgroundColor: "#EF4444" }} />
      </div>
      <div className="flex justify-between mt-1.5 text-xs">
        <span className="text-emerald-400 font-stat font-bold">{labels[0]} {av}%</span>
        <span className="text-slate-400 font-stat font-bold">{labels[1]} {bv}%</span>
        <span className="text-red-400 font-stat font-bold">{labels[2]} {cv}%</span>
      </div>
    </div>
  );
}

export default function Stats() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/stats").then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-6 space-y-4"><Skeleton className="h-40 rounded-xl bg-slate-800/50" /><Skeleton className="h-64 rounded-xl bg-slate-800/50" /></div>;
  if (!d?.disponible) return <div className="max-w-3xl mx-auto px-4 py-10 text-center text-slate-400">Statistiques indisponibles pour le moment.</div>;

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1 flex items-center gap-2">
        <PieChart className="w-7 h-7 text-emerald-400" /> Stats
      </h1>
      <p className="text-slate-400 text-sm mb-6">
        Lien entre les notes des équipes et les résultats réels · échantillon de <b className="text-slate-200">{d.echantillon}</b> matchs terminés.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div className="card-surface rounded-xl p-5" data-testid="stat-higher-rated">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <h3 className="font-head font-bold text-slate-100">Équipe la mieux notée</h3>
          </div>
          <div className="text-3xl font-black font-stat text-emerald-400 mb-1">{d.note_superieure.victoires_pct}%</div>
          <p className="text-xs text-slate-500 mb-3">de victoires quand une équipe a une note supérieure</p>
          <TriBar a={d.note_superieure.victoires_pct} b={d.note_superieure.nuls_pct} c={d.note_superieure.defaites_pct}
            labels={["Gagne", "Nul", "Perd"]} />
        </div>

        <div className="card-surface rounded-xl p-5" data-testid="stat-home-advantage">
          <div className="flex items-center gap-2 mb-3">
            <HomeIcon className="w-5 h-5 text-emerald-400" />
            <h3 className="font-head font-bold text-slate-100">Avantage du terrain</h3>
          </div>
          <div className="text-3xl font-black font-stat text-emerald-400 mb-1">{d.avantage_domicile.domicile_pct}%</div>
          <p className="text-xs text-slate-500 mb-3">de victoires pour l'équipe à domicile</p>
          <TriBar a={d.avantage_domicile.domicile_pct} b={d.avantage_domicile.nul_pct} c={d.avantage_domicile.exterieur_pct}
            labels={["Domicile", "Nul", "Extérieur"]} />
        </div>
      </div>

      <div className="card-surface rounded-xl p-5" data-testid="stat-by-gap">
        <div className="flex items-center gap-2 mb-4">
          <Scale className="w-5 h-5 text-emerald-400" />
          <h3 className="font-head font-bold text-slate-100">Résultat selon l'écart de notes</h3>
        </div>
        <div className="space-y-4">
          {d.par_ecart_note.map((b) => (
            <div key={b.tranche} data-testid={`stat-gap-${b.tranche}`}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-semibold text-slate-200">Écart {b.tranche} pts</span>
                <span className="text-xs text-slate-500 font-stat">{b.matchs} matchs</span>
              </div>
              {b.matchs > 0 ? (
                <>
                  <TriBar a={b.note_sup_gagne_pct} b={b.nul_pct} c={b.note_inf_gagne_pct}
                    labels={["Note sup.", "Nul", "Note inf."]} />
                  {b.scores_frequents?.length > 0 && (
                    <div className="mt-2.5" data-testid={`stat-scores-${b.tranche}`}>
                      <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
                        Scores exacts fréquents <span className="text-slate-600">(vue équipe mieux notée)</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {b.scores_frequents.map((s) => (
                          <span key={s.score}
                            className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/70 border border-slate-700 px-2 py-1"
                            data-testid={`stat-score-${b.tranche}-${s.score}`}>
                            <span className="font-stat font-bold text-slate-100 text-sm tabular-nums">{s.score}</span>
                            <span className="text-[11px] text-emerald-400 font-stat">{s.pct}%</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-slate-600">Pas assez de données</p>
              )}
            </div>
          ))}
        </div>
        <p className="text-[11px] text-slate-500 mt-4">{d.note}</p>
      </div>
    </div>
  );
}
