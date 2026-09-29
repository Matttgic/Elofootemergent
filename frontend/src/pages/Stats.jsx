import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui/skeleton";
import { BetsList } from "../components/BetsList";
import { PieChart, TrendingUp, Home as HomeIcon, Scale, Coins, Clock, Target, AlertTriangle, Award } from "lucide-react";
import { Link } from "react-router-dom";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { MethodRanking } from "../components/Forecast";

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

function GapList({ rows, prefix, unit, labels, fav }) {
  return (
    <div className="space-y-4">
      {rows.map((b) => (
        <div key={b.tranche} data-testid={`${prefix}-gap-${b.tranche}`}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm font-semibold text-slate-200">Écart {b.tranche} {unit}</span>
            <span className="text-xs text-slate-500 font-stat">{b.matchs} matchs</span>
          </div>
          {b.matchs > 0 ? (
            <>
              <TriBar a={b.favori_gagne_pct} b={b.nul_pct} c={b.outsider_gagne_pct} labels={labels} />
              {b.scores_frequents?.length > 0 && (
                <div className="mt-2.5" data-testid={`${prefix}-scores-${b.tranche}`}>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
                    Scores exacts fréquents <span className="text-slate-600">(vue {fav})</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {b.scores_frequents.map((s) => (
                      <span key={s.score}
                        className="inline-flex items-center gap-1.5 rounded-md bg-slate-800/70 border border-slate-700 px-2 py-1"
                        data-testid={`${prefix}-score-${b.tranche}-${s.score}`}>
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
  );
}

const NOTE_LABELS = ["Mieux notée", "Nul", "Moins bien notée"];
const VENUES = { tous: "Tous", domicile: "À domicile", exterieur: "À l'extérieur" };
const VENUE_TEXT = { tous: "Tous terrains confondus", domicile: "Quand elle joue à domicile",
                     exterieur: "Quand elle joue à l'extérieur" };
const MIN_COMPARABLE = 20;

// « Si une équipe notée 78 reçoit une équipe notée 50 » : tranche d'écart et terrain correspondants
function NoteSimulator({ par }) {
  const [dom, setDom] = useState("78");
  const [ext, setExt] = useState("50");
  const a = Number(dom), b = Number(ext);
  const valid = dom !== "" && ext !== "" && a >= 0 && a <= 100 && b >= 0 && b <= 100;
  const gap = Math.abs(a - b);
  const venue = a > b ? "domicile" : "exterieur";
  const row = valid && a !== b
    ? par[venue].find((r) => gap >= r.min && (r.max === null || gap < r.max)) : null;
  const input = (value, set, testid) => (
    <input type="number" min="0" max="100" inputMode="numeric" value={value} data-testid={testid}
      onChange={(e) => set(e.target.value.slice(0, 3))}
      className="w-14 rounded-md bg-slate-900 border border-slate-700 px-2 py-1 text-center font-stat font-bold text-slate-100 focus:outline-none focus:border-cyan-500" />
  );

  return (
    <div className="rounded-lg bg-slate-800/40 border border-slate-700/70 p-3 mb-4" data-testid="note-simulator">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 text-sm text-slate-300">
        <span>Une équipe notée</span>{input(dom, setDom, "note-sim-home")}
        <span>reçoit une équipe notée</span>{input(ext, setExt, "note-sim-away")}
      </div>
      <div className="mt-2.5 text-xs text-slate-400" data-testid="note-sim-result">
        {!valid ? "Notes entre 0 et 100."
          : a === b ? "Notes égales : aucune équipe n'est mieux notée."
          : !row || row.matchs < MIN_COMPARABLE ? `Trop peu de matchs comparables (écart ${gap}, ${row?.matchs ?? 0} matchs).`
          : (
            <>
              <div className="mb-2">
                Écart de <b className="text-slate-200">{gap}</b>, l'équipe la mieux notée joue{" "}
                <b className="text-slate-200">{venue === "domicile" ? "à domicile" : "à l'extérieur"}</b> :
                sur <b className="text-slate-200">{row.matchs}</b> matchs comparables (écart {row.tranche}) :
              </div>
              <TriBar a={row.favori_gagne_pct} b={row.nul_pct} c={row.outsider_gagne_pct} labels={NOTE_LABELS} />
            </>
          )}
      </div>
    </div>
  );
}

function NoteGaps({ notes }) {
  const [venue, setVenue] = useState("tous");
  const split = notes.mieux_notee[venue];
  return (
    <div data-testid="note-gaps">
      <NoteSimulator par={notes.par_ecart} />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-xs text-slate-500">Terrain de la mieux notée :</span>
        {Object.entries(VENUES).map(([k, label]) => (
          <button key={k} onClick={() => setVenue(k)} data-testid={`note-venue-${k}`}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              venue === k ? "bg-cyan-500 text-slate-900" : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"}`}>
            {label}
          </button>
        ))}
      </div>
      <p className="text-xs text-slate-400 mb-4" data-testid="note-venue-summary">
        {VENUE_TEXT[venue]}, l'équipe la mieux notée gagne{" "}
        <b className="text-emerald-400">{split.victoires_pct}%</b> des matchs, fait nul {split.nuls_pct}% et perd{" "}
        {split.defaites_pct}% ({split.matchs} matchs).
      </p>
      <GapList rows={notes.par_ecart[venue]} prefix={`note-${venue}`} unit="pts de note"
        labels={NOTE_LABELS} fav="de la mieux notée" />
      <p className="text-[11px] text-slate-500 mt-4">{notes.note}</p>
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
    <div className="card-surface rounded-xl p-5" data-testid="stat-bet-simulation">
      <div className="flex items-center gap-2 mb-1">
        <Coins className="w-5 h-5 text-amber-400" />
        <h3 className="font-head font-bold text-slate-100">Simulation de paris</h3>
      </div>
      <p className="text-xs text-slate-500 mb-3">{sim.regles}</p>
      <div className="rounded-lg bg-amber-500/5 border border-amber-500/30 p-3 mb-4 flex items-start gap-2.5 text-xs text-slate-300" data-testid="sim-backtest-warning">
        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
        <span>
          <b className="text-amber-300">Test sur l'historique :</b> sur 13 273 matchs de 8 championnats (2021 à 2026), parier le
          favori du modèle aux cotes Bet365 aurait perdu <b>4,6 %</b> des mises, et les paris « value » de <b>8,8 à 13,9 %</b>.
          Les bookmakers restent plus précis que le modèle : cette simulation mesure le modèle, ce n'est pas un conseil de pari.
        </span>
      </div>

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

          {s.clv?.paris > 0 && (
            <p className="text-xs text-slate-400 mb-4" data-testid="sim-clv">
              Valeur de clôture (CLV) : <b className={s.clv.moyenne_pct > 0 ? "text-emerald-400" : "text-red-400"}>
                {s.clv.moyenne_pct > 0 ? "+" : ""}{s.clv.moyenne_pct}%</b> en moyenne sur {s.clv.paris} paris ;
              {" "}{s.clv.positifs_pct}% pris à une meilleure cote que la dernière relevée avant le match.
              <span className="text-slate-500"> Une CLV positive durable est le meilleur signe d'un avantage réel.</span>
            </p>
          )}
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-2">Détail par probabilité du favori (modèle)</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase text-slate-500 text-left border-b border-slate-800">
                  <th className="py-1.5 pr-2">Proba.</th>
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
      {sim.annules > 0 && (
        <p className="text-[11px] text-slate-500 mt-1" data-testid="sim-voided">
          {sim.annules} paris annulés (match annulé ou reporté au-delà de 72 h, mise remboursée).
        </p>
      )}
      {sim.paris_anciens_exclus > 0 && (
        <p className="text-[11px] text-slate-500 mt-1" data-testid="sim-old-excluded">
          {sim.paris_anciens_exclus} paris figés avec un ancien modèle sont exclus du bilan.
        </p>
      )}
    </div>
  );
}

function ModelQuality({ q }) {
  if (!q) return null;
  const better = q.modele.log_loss < q.reference.log_loss;
  return (
    <div className="card-surface rounded-xl p-5 mb-4" data-testid="stat-model-quality">
      <div className="flex items-center gap-2 mb-1">
        <Target className="w-5 h-5 text-cyan-400" />
        <h3 className="font-head font-bold text-slate-100">Le Pronostic FootPulse cette saison</h3>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        {q.matchs} matchs, probabilités calculées avant chaque coup d'envoi
        {q.hors_echantillon ? " avec un modèle ajusté sur les saisons précédentes uniquement" : ""}
        {q.avec_xg_pct ? `, dont ${Math.round(q.avec_xg_pct)} % avec la forme xG` : ""}. Log-loss et Brier : plus c'est bas, mieux c'est.
      </p>
      <div className="grid grid-cols-3 gap-3 mb-4 text-center">
        {[["Log-loss", "log_loss"], ["Brier", "brier"], ["Réussite", "reussite_pct"]].map(([label, k]) => (
          <div key={k} className="rounded-lg bg-slate-800/50 p-3" data-testid={`quality-${k}`}>
            <div className="text-[10px] uppercase text-slate-500">{label}</div>
            <div className="text-xl font-black font-stat text-cyan-400">{q.modele[k]}{k === "reussite_pct" ? "%" : ""}</div>
            <div className="text-[11px] text-slate-500">référence {q.reference[k]}{k === "reussite_pct" ? "%" : ""}</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-400 mb-3">
        Référence = simples fréquences domicile / nul / extérieur. {better
          ? "Le pronostic fait mieux que cette référence."
          : "Le modèle ne fait pas mieux que cette référence sur cet échantillon."}
      </p>
      {q.note_100 && (
        <div className="mb-4" data-testid="quality-note">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-2">
            Et la note /100 ? Mêmes {q.note_100.matchs} matchs
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase text-slate-500 text-left border-b border-slate-800">
                <th className="py-1.5 pr-2">Probabilités</th>
                <th className="py-1.5 px-2 text-right whitespace-nowrap">Log-loss</th>
                <th className="py-1.5 px-2 text-right">Brier</th>
                <th className="py-1.5 pl-2 text-right">Réussite</th>
              </tr>
            </thead>
            <tbody>
              {[[q.avec_xg_pct ? "Modèle du site (Elo + xG)" : "Modèle du site (Elo)", q.note_100.modele, "text-cyan-300 font-semibold", "model"],
                ["Note /100 seule", q.note_100.note, "text-slate-200", "note"],
                ["Référence (fréquences)", q.note_100.reference, "text-slate-400", "reference"]].map(([label, v, cls, k]) => (
                <tr key={k} className={`border-b border-slate-800/60 ${cls}`} data-testid={`quality-note-${k}`}>
                  <td className="py-1.5 pr-2">{label}</td>
                  <td className="py-1.5 px-2 text-right font-stat">{v.log_loss}</td>
                  <td className="py-1.5 px-2 text-right font-stat">{v.brier}</td>
                  <td className="py-1.5 pl-2 text-right font-stat">{v.reussite_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-slate-500 mt-2">
            Note /100 seule : probabilités tirées du seul écart des notes globales avant le match
            {q.note_100.hors_echantillon ? ", modèle ajusté sur les saisons précédentes" : ""}. Sur l'historique, ajouter la note
            à l'Elo n'améliore pas les prévisions (détail dans la page Méthode).
          </p>
        </div>
      )}
      <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-2">Calibration : le favori gagne-t-il aussi souvent que prévu ?</div>
      <table className="w-full text-sm" data-testid="quality-calibration">
        <thead>
          <tr className="text-[10px] uppercase text-slate-500 text-left border-b border-slate-800">
            <th className="py-1.5 pr-2">Proba. du favori</th>
            <th className="py-1.5 px-2 text-right">Matchs</th>
            <th className="py-1.5 px-2 text-right">Prévu</th>
            <th className="py-1.5 pl-2 text-right">Observé</th>
          </tr>
        </thead>
        <tbody>
          {q.calibration.filter((c) => c.matchs > 0).map((c) => (
            <tr key={c.tranche} className="border-b border-slate-800/60">
              <td className="py-1.5 pr-2 text-slate-300">{c.tranche}</td>
              <td className="py-1.5 px-2 text-right font-stat text-slate-400">{c.matchs}</td>
              <td className="py-1.5 px-2 text-right font-stat text-slate-300">{c.prevu_pct}%</td>
              <td className="py-1.5 pl-2 text-right font-stat text-emerald-400">{c.observe_pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Stats() {
  const [d, setD] = useState(null);
  const [sim, setSim] = useState(null);
  const [ranking, setRanking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [gapKind, setGapKind] = useState("elo");
  const [tab, setTab] = useState("fiabilite");

  useEffect(() => {
    api.get("/stats").then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
    api.get("/bets/simulation").then((r) => setSim(r.data)).catch(() => setSim(null));
    api.get("/scoring/config").then((r) => setRanking(r.data?.elo?.backtest?.classement || null)).catch(() => {});
  }, []);

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-6 space-y-4"><Skeleton className="h-40 rounded-xl bg-slate-800/50" /><Skeleton className="h-64 rounded-xl bg-slate-800/50" /></div>;
  if (!d?.disponible) return <div className="max-w-3xl mx-auto px-4 py-10 text-center text-slate-400">Statistiques indisponibles pour le moment.</div>;

  const site = ranking?.methodes.find((m) => m.site);
  const note = ranking?.methodes.find((m) => m.id === "note");
  const triggerCls = "data-[state=active]:bg-emerald-500 data-[state=active]:text-white text-xs sm:text-sm";

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1 flex items-center gap-2">
        <PieChart className="w-7 h-7 text-emerald-400" /> Stats
      </h1>
      <p className="text-slate-400 text-sm mb-6">
        Quelle méthode prévoit le mieux les matchs, et ce que donne le pronostic cette saison · <b className="text-slate-200">{d.echantillon}</b> matchs analysés
        {d.echantillon_saison ? <> dont <b className="text-slate-200">{d.echantillon_saison}</b> cette saison</> : null}.
      </p>

      {ranking && (
        <div className="card-surface rounded-xl p-5 mb-5 border border-emerald-500/20" data-testid="stat-ranking">
          <div className="flex items-center gap-2 mb-1">
            <Award className="w-5 h-5 text-emerald-400" />
            <h2 className="font-head text-lg font-bold text-slate-50">Quelle méthode prévoit le mieux ?</h2>
          </div>
          {site && note && (
            <p className="text-sm text-slate-300 mb-4" data-testid="stat-ranking-summary">
              Le <b className="text-emerald-300">Pronostic FootPulse</b> (force Elo + forme xG) est notre meilleure méthode :
              indice <b className="text-slate-50">{site.indice}</b>, contre {note.indice} pour la note de forme /100.
              Seules les cotes des bookmakers font mieux.
            </p>
          )}
          <MethodRanking classement={ranking} />
          <Link to="/methodologie#classement" className="inline-block mt-2 text-xs text-emerald-400 hover:text-emerald-300">
            Détail des tests →
          </Link>
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-slate-900/60 border border-slate-800 flex-wrap h-auto mb-4">
          <TabsTrigger value="fiabilite" data-testid="stats-tab-fiabilite" className={triggerCls}>
            <Target className="w-4 h-4 mr-1.5" /> Fiabilité cette saison
          </TabsTrigger>
          <TabsTrigger value="ecarts" data-testid="stats-tab-ecarts" className={triggerCls}>
            <Scale className="w-4 h-4 mr-1.5" /> Résultats par écart
          </TabsTrigger>
          <TabsTrigger value="paris" data-testid="stats-tab-paris" className={triggerCls}>
            <Coins className="w-4 h-4 mr-1.5" /> Paris simulés
          </TabsTrigger>
        </TabsList>

        <TabsContent value="fiabilite">
          <ModelQuality q={d.modele} />
        </TabsContent>

        <TabsContent value="ecarts">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div className="card-surface rounded-xl p-5" data-testid="stat-higher-rated">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
                <h3 className="font-head font-bold text-slate-100">Favori selon l'Elo</h3>
              </div>
              <div className="text-3xl font-black font-stat text-emerald-400 mb-1">{d.favori_elo.victoires_pct}%</div>
              <p className="text-xs text-slate-500 mb-3">de victoires pour l'équipe au meilleur Elo (avantage du terrain compris)</p>
              <TriBar a={d.favori_elo.victoires_pct} b={d.favori_elo.nuls_pct} c={d.favori_elo.defaites_pct}
                labels={["Gagne", "Nul", "Perd"]} />
            </div>

            {d.notes?.disponible && (
              <div className="card-surface rounded-xl p-5" data-testid="stat-better-note">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp className="w-5 h-5 text-slate-400" />
                  <h3 className="font-head font-bold text-slate-100">Mieux notée (forme /100)</h3>
                </div>
                <div className="text-3xl font-black font-stat text-slate-200 mb-1">{d.notes.mieux_notee.tous.victoires_pct}%</div>
                <p className="text-xs text-slate-500 mb-3">
                  de victoires pour l'équipe à la meilleure note de forme (domicile {d.notes.mieux_notee.domicile.victoires_pct}%,
                  extérieur {d.notes.mieux_notee.exterieur.victoires_pct}%)
                </p>
                <TriBar a={d.notes.mieux_notee.tous.victoires_pct} b={d.notes.mieux_notee.tous.nuls_pct}
                  c={d.notes.mieux_notee.tous.defaites_pct} labels={["Gagne", "Nul", "Perd"]} />
              </div>
            )}

            <div className="card-surface rounded-xl p-5 sm:col-span-2" data-testid="stat-home-advantage">
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
            <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
              <div className="flex items-center gap-2">
                <Scale className="w-5 h-5 text-emerald-400" />
                <h3 className="font-head font-bold text-slate-100">Résultat selon l'écart</h3>
              </div>
              {d.notes?.disponible && (
                <div className="flex rounded-lg bg-slate-800/60 p-0.5">
                  {[["elo", "Force Elo"], ["note", "Forme /100"]].map(([k, label]) => (
                    <button key={k} onClick={() => setGapKind(k)} data-testid={`gap-kind-${k}`}
                      className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
                        gapKind === k ? "bg-emerald-500 text-white" : "text-slate-400 hover:text-slate-200"}`}>
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {gapKind === "note" && d.notes?.disponible ? <NoteGaps notes={d.notes} /> : (
              <>
                <GapList rows={d.par_ecart_elo} prefix="stat" unit="pts" labels={["Favori", "Nul", "Outsider"]}
                  fav="du favori" />
                <p className="text-[11px] text-slate-500 mt-4">{d.note}</p>
              </>
            )}
          </div>
        </TabsContent>

        <TabsContent value="paris">
          <BetSimulation sim={sim} />
          <BetsList />
        </TabsContent>
      </Tabs>
    </div>
  );
}
