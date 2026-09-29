import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui/skeleton";
import { BookOpen, ShieldCheck, Scale, Activity, AlertTriangle } from "lucide-react";

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

  const eq = c.equipes || {};
  const jo = c.joueurs || {};

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
            <p className="text-sm text-slate-300 leading-relaxed">{eq.principe}</p>
          </div>
        </div>
        <div className="card-surface rounded-xl p-5 border-emerald-500/20 bg-emerald-500/5">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-emerald-300 text-sm mb-1">Protection anti-biais</div>
              <p className="text-sm text-slate-300 leading-relaxed">{eq.anti_biais}</p>
            </div>
          </div>
        </div>

        {c.elo && (
          <>
            <h2 className="font-head text-xl font-bold text-slate-100 pt-2">Notes Elo et probabilités</h2>
            <div className="card-surface rounded-xl p-5 space-y-3" data-testid="methodo-elo">
              <div className="flex items-start gap-3">
                <Activity className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                <div className="space-y-2">
                  <p className="text-sm text-slate-300 leading-relaxed">{c.elo.principe}</p>
                  <p className="text-sm text-slate-400 leading-relaxed">{c.elo.probabilites}</p>
                  {c.elo.xg && <p className="text-sm text-slate-400 leading-relaxed" data-testid="methodo-xg">{c.elo.xg}</p>}
                </div>
              </div>
            </div>
            <div className="card-surface rounded-xl p-5" data-testid="methodo-backtest">
              <h3 className="font-head font-bold text-slate-100 mb-1">Test sur l'historique</h3>
              <p className="text-xs text-slate-500 mb-3">
                {c.elo.backtest.matchs.toLocaleString("fr-FR")} matchs ({c.elo.backtest.periode}) :{" "}
                {c.elo.backtest.championnats}. Chaque saison est prédite avec un modèle ajusté sur les saisons précédentes.
                Log-loss : plus c'est bas, plus les probabilités sont justes.
              </p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase text-slate-500 text-left border-b border-slate-800">
                    <th className="py-1.5 pr-2">Méthode</th>
                    <th className="py-1.5 px-2 text-right">Log-loss</th>
                    <th className="py-1.5 pl-2 text-right">Réussite</th>
                  </tr>
                </thead>
                <tbody>
                  {c.elo.backtest.log_loss.map((r) => (
                    <tr key={r.modele} className={`border-b border-slate-800/60 ${r.modele === "Elo (site)" ? "text-cyan-300 font-semibold" : "text-slate-300"}`}>
                      <td className="py-1.5 pr-2">{r.modele}</td>
                      <td className="py-1.5 px-2 text-right font-stat">{r.valeur.toFixed(3)}</td>
                      <td className="py-1.5 pl-2 text-right font-stat">{r.reussite_pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {c.elo.backtest.xg && (
                <div className="mt-4" data-testid="methodo-backtest-xg">
                  <p className="text-xs text-slate-500 mb-2">
                    Apport des xG : {c.elo.backtest.xg.matchs.toLocaleString("fr-FR")} matchs ({c.elo.backtest.xg.championnats}).
                  </p>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[10px] uppercase text-slate-500 text-left border-b border-slate-800">
                        <th className="py-1.5 pr-2">Méthode</th>
                        <th className="py-1.5 px-2 text-right">Log-loss</th>
                        <th className="py-1.5 pl-2 text-right">Brier</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.elo.backtest.xg.log_loss.map((r) => (
                        <tr key={r.modele} className={`border-b border-slate-800/60 ${r.modele.includes("(site)") ? "text-cyan-300 font-semibold" : "text-slate-300"}`}>
                          <td className="py-1.5 pr-2">{r.modele}</td>
                          <td className="py-1.5 px-2 text-right font-stat">{r.valeur.toFixed(3)}</td>
                          <td className="py-1.5 pl-2 text-right font-stat">{r.brier.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="mt-4 rounded-lg bg-amber-500/5 border border-amber-500/30 p-3 flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="text-xs text-slate-300 space-y-1">
                  <p>{c.elo.value}</p>
                  {c.elo.backtest.paris_roi_pct.map((p) => (
                    <p key={p.strategie} className="font-stat">{p.strategie} : <b className="text-red-400">{p.roi} %</b> de rendement</p>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        <h2 className="font-head text-xl font-bold text-slate-100 pt-2">Scores des équipes (note /100)</h2>
        <WeightBlock title="Score global — pondération" weights={eq.score_global} />
        <WeightBlock title="Score offensif — pondération" weights={eq.score_offensif} />
        <WeightBlock title="Score défensif — pondération" weights={eq.score_defensif} />

        <h2 className="font-head text-xl font-bold text-slate-100 pt-2">Scores des joueurs</h2>
        <div className="card-surface rounded-xl p-5 space-y-2">
          <p className="text-sm text-slate-300 leading-relaxed">{jo.source}</p>
          <p className="text-sm text-slate-400 leading-relaxed">{jo.normalisation}</p>
          <p className="text-sm text-slate-400 leading-relaxed">{jo.ajustement_echantillon}</p>
          <p className="text-xs text-slate-500 leading-relaxed">{jo.couverture}</p>
        </div>
        <WeightBlock title="Score joueur — pondération" weights={jo.score_joueur} />

        <div className="card-surface rounded-xl p-5">
          <h3 className="font-head font-bold text-slate-100 mb-2">Données indisponibles (équipes)</h3>
          <div className="flex flex-wrap gap-2 mb-3">
            {(eq.donnees_indisponibles || []).map((d) => (
              <span key={d} className="text-xs bg-slate-800 text-slate-400 border border-slate-700 rounded px-2 py-0.5 font-stat">{d}</span>
            ))}
          </div>
          <p className="text-xs text-slate-500">{eq.note_donnees}</p>
        </div>
      </div>
    </div>
  );
}
