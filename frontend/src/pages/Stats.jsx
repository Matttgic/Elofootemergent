import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui/skeleton";
import { PieChart, TrendingUp, Home as HomeIcon, Scale, Coins, Clock } from "lucide-react";

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

function Money({ v }) {
  const pos = v > 0, neg = v < 0;
  return <span className={`font-stat font-bold tabular-nums ${pos ? "text-emerald-400" : neg ? "text-red-400" : "text-slate-300"}`}>
    {pos ? "+" : ""}{v?.toFixed ? v.toFixed(1) : v} u
  </span>;
}

function BetSimulation({ sim }) {
  const [strat, setStrat] = useState("favori");
  const [stake, setStake] = useState("mise_fixe");
  if (!sim) return null;
  const s = sim.strategies[strat];
  const t = s.total[stake];
  const stratLabel = { favori: "Favori", value: "Value" };
  const stakeLabel = { mise_fixe: "Mise fixe (1 u)", kelly: "¼ Kelly (bankroll 100 u)" };

  return (
    <div className="card-surface rounded-xl p-5 mt-4" data-testid="stat-bet-simulation">
      <div className="flex items-center gap-2 mb-1">
        <Coins className="w-5 h-5 text-amber-400" />
        <h3 className="font-head font-bold text-slate-100">Simulation de paris</h3>
      </div>
      <p className="text-xs text-slate-500 mb-4">{sim.regles}</p>

      <div className="flex flex-wrap gap-2 mb-4">
        {["favori", "value"].map((k) => (
          <button key={k} onClick={() => setStrat(k)} data-testid={`sim-strat-${k}`}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              strat === k ? "bg-amber-500 text-slate-900" : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"}`}>
            {stratLabel[k]}
          </button>
        ))}
        <span className="w-px h-5 bg-slate-700 mx-1" />
        {["mise_fixe", "kelly"].map((k) => (
          <button key={k} onClick={() => setStake(k)} data-testid={`sim-stake-${k}`}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              stake === k ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"}`}>
            {stakeLabel[k]}
          </button>
        ))}
      </div>

      {!sim.disponible ? (
        <div className="rounded-lg bg-slate-800/50 border border-slate-700 p-4 flex items-center gap-3" data-testid="sim-pending">
          <Clock className="w-5 h-5 text-cyan-400 shrink-0" />
          <p className="text-sm text-slate-300">
            <b className="text-slate-100">{sim.en_attente} paris en attente.</b> Les cotes réelles sont figées pour les matchs à venir ;
            le bilan gains/pertes s'affichera dès que ces matchs seront joués.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4" data-testid="sim-total">
            <div className="rounded-lg bg-slate-800/50 p-3">
              <div className="text-[10px] uppercase text-slate-500">Paris réglés</div>
              <div className="text-xl font-black font-stat text-slate-100">{s.total.paris}</div>
              <div className="text-[11px] text-slate-500">{s.total.gagnes} gagnés</div>
            </div>
            <div className="rounded-lg bg-slate-800/50 p-3">
              <div className="text-[10px] uppercase text-slate-500">Taux de réussite</div>
              <div className="text-xl font-black font-stat text-cyan-400">{s.total.taux_reussite}%</div>
              <div className="text-[11px] text-slate-500">book {stake === "kelly" ? "¼ Kelly" : "1 u/match"}</div>
            </div>
            <div className="rounded-lg bg-slate-800/50 p-3">
              <div className="text-[10px] uppercase text-slate-500">Gain net</div>
              <div className="text-xl"><Money v={t.gain_net} /></div>
              <div className="text-[11px] text-slate-500">ROI {t.roi}%</div>
            </div>
            <div className="rounded-lg bg-slate-800/50 p-3">
              <div className="text-[10px] uppercase text-slate-500">Bankroll (dép. 100 u)</div>
              <div className={`text-xl font-black font-stat tabular-nums ${t.bankroll >= 100 ? "text-emerald-400" : "text-red-400"}`}>{t.bankroll}</div>
              <div className="text-[11px] text-slate-500">misé {t.mise_totale} u</div>
            </div>
          </div>

          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-2">Détail par tranche d'écart</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase text-slate-500 text-left border-b border-slate-800">
                  <th className="py-1.5 pr-2">Écart</th>
                  <th className="py-1.5 px-2 text-right">Paris</th>
                  <th className="py-1.5 px-2 text-right">Réussite</th>
                  <th className="py-1.5 px-2 text-right">Gain net</th>
                  <th className="py-1.5 pl-2 text-right">ROI</th>
                </tr>
              </thead>
              <tbody>
                {s.par_ecart.map((r) => (
                  <tr key={r.tranche} className="border-b border-slate-800/60" data-testid={`sim-row-${r.tranche}`}>
                    <td className="py-1.5 pr-2 text-slate-300">{r.tranche}</td>
                    <td className="py-1.5 px-2 text-right font-stat text-slate-400">{r.paris}</td>
                    <td className="py-1.5 px-2 text-right font-stat text-cyan-400">{r.taux_reussite}%</td>
                    <td className="py-1.5 px-2 text-right"><Money v={r[stake].gain_net} /></td>
                    <td className="py-1.5 pl-2 text-right font-stat text-slate-300">{r[stake].roi}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sim.en_attente > 0 && (
            <p className="text-[11px] text-slate-500 mt-3">+ {sim.en_attente} paris en attente (matchs à venir).</p>
          )}
        </>
      )}
      {sim.paris_anciens_exclus > 0 && (
        <p className="text-[11px] text-slate-500 mt-1" data-testid="sim-old-excluded">
          {sim.paris_anciens_exclus} paris figés avec l'ancien modèle (probabilités biaisées) sont exclus du bilan.
        </p>
      )}
    </div>
  );
}

function sTaux(s) { return s.total.mise_fixe.taux_reussite; }

export default function Stats() {
  const [d, setD] = useState(null);
  const [sim, setSim] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/stats").then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
    api.get("/bets/simulation").then((r) => setSim(r.data)).catch(() => setSim(null));
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

      <BetSimulation sim={sim} />
    </div>
  );
}
