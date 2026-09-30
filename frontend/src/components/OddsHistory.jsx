import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { History, TrendingUp } from "lucide-react";
import { api } from "../lib/api";

// Blocs communs à la page « Cotes » et à la fiche match : ce qui s'est passé dans les
// matchs passés aux mêmes cotes (historique Pinnacle, voir backend/cotes_historiques.py).

export const fmt = (v, d = 1) => (v == null ? "—" : Number(v).toFixed(d).replace(".", ","));
export const fmtInt = (v) => (v == null ? "—" : Number(v).toLocaleString("fr-FR"));
export const signed = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmt(v)} %`);

// Le décompte : victoires à domicile, nuls, victoires à l'extérieur des matchs trouvés.
export function OutcomeCounts({ s, testid = "cotes-resume" }) {
  return (
    <div className="grid grid-cols-3 gap-2 text-center" data-testid={testid}>
      {[["domicile", "Victoire à domicile", "text-emerald-300"], ["nul", "Match nul", "text-slate-200"],
        ["exterieur", "Victoire à l'extérieur", "text-cyan-300"]].map(([k, l, c]) => (
        <div key={k} className="rounded-lg bg-slate-900/60 py-3 px-1" data-testid={`resume-${k}`}>
          <div className={`font-stat font-black text-3xl sm:text-4xl leading-none ${c}`}>{fmtInt(s.issues[k].matchs)}</div>
          <div className="text-[11px] text-slate-300 mt-1.5">{l}</div>
          <div className="font-stat text-sm text-slate-400 mt-0.5">{fmt(s.issues[k].reel_pct, 0)} %</div>
        </div>
      ))}
    </div>
  );
}

// Scores exacts les plus fréquents (score domicile - extérieur).
export function ScoreChips({ scores, label = "Scores les plus fréquents", testid }) {
  if (!scores?.length) return null;
  return (
    <div className="mt-3 flex items-center gap-1.5 flex-wrap text-xs text-slate-400" data-testid={testid}>
      <span className="mr-0.5">{label} :</span>
      {scores.map((sc) => (
        <span key={sc.score} className="font-stat bg-slate-800 rounded px-2 py-0.5 text-slate-200" title={`${fmtInt(sc.matchs)} matchs`}>
          {sc.score} <span className="text-slate-500">{fmt(sc.pct, 0)}%</span>
        </span>
      ))}
    </div>
  );
}

// Résumé : chaque source vue depuis le match demandé (1 / N / 2), puis tous ces matchs
// mis ensemble (chacun compté une fois) et la tendance qui en ressort.
export function Tendance({ d, test, nested = false }) {
  const t = d.tendance;
  if (!t) return null;
  const known = (e) => (e?.trouvee && e.matchs > 0 ? e : null);
  const home = known(d.equipe_domicile), away = known(d.equipe_exterieur);
  const nomDom = d.equipe_domicile?.trouvee ? d.equipe_domicile.nom : "Domicile";
  const nomExt = d.equipe_exterieur?.trouvee ? d.equipe_exterieur.nom : "Extérieur";
  const sim = d.similaires;
  const rows = [];
  if (sim.matchs) {
    rows.push({ key: "similaires", label: "Tous les matchs à ces cotes", n: sim.matchs,
      v: [sim.issues.domicile.matchs, sim.issues.nul.matchs, sim.issues.exterieur.matchs] });
  }
  if (home) {
    rows.push({ key: "domicile", label: `${home.nom} à une cote proche de ${fmt(d.cotes.domicile, 2)}`, n: home.matchs,
      v: [home.victoires, home.nuls, home.defaites], sub: ["victoires", "nuls", "défaites"] });
  }
  if (away) {
    rows.push({ key: "exterieur", label: `${away.nom} à une cote proche de ${fmt(d.cotes.exterieur, 2)}`, n: away.matchs,
      v: [away.defaites, away.nuls, away.victoires], sub: ["défaites", "nuls", "victoires"] });
  }
  const top = (v) => v.indexOf(Math.max(...v));
  const issueName = (k) => [`victoire de ${nomDom}`, "match nul", `victoire de ${nomExt}`][k]
    .replace("victoire de Domicile", "victoire à domicile").replace("victoire de Extérieur", "victoire à l'extérieur");
  const tops = rows.map((r) => top(r.v));
  const accord = tops.every((k) => k === tops[0]);
  const tv = [t.domicile, t.nul, t.exterieur];
  const tk = top(tv);
  const cell = (x, n, sub) => (
    <div className="text-right leading-tight whitespace-nowrap">
      <div className="font-stat text-slate-100">{fmtInt(x)}</div>
      <div className="font-stat text-[11px] text-slate-500">{fmt(100 * x / n, 0)} %{sub ? <span className="text-slate-600 font-sans"> {sub}</span> : null}</div>
    </div>
  );
  return (
    <div className={nested ? "border-t border-slate-800 pt-4" : "card-surface rounded-xl p-5 border border-emerald-500/20"}
      data-testid="cotes-tendance">
      <h2 className="font-head text-lg font-bold text-slate-50 flex items-center gap-2 mb-3">
        <TrendingUp className="w-5 h-5 text-emerald-400" /> Résumé et tendance
      </h2>
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 sm:gap-x-4 gap-y-2 items-center text-sm">
        <div />
        {[`1 · ${nomDom}`, "N · Nul", `2 · ${nomExt}`].map((h) => (
          <div key={h} className="text-[10px] uppercase tracking-wide text-slate-500 text-right max-w-[5.5rem] truncate">{h}</div>
        ))}
        {rows.map((r) => (
          <div key={r.key} className="contents" data-testid={`tendance-${r.key}`}>
            <div className="text-xs text-slate-300 leading-tight">{r.label} <span className="text-slate-500">({fmtInt(r.n)} matchs)</span></div>
            {r.v.map((x, j) => <div key={j}>{cell(x, r.n, r.sub?.[j])}</div>)}
          </div>
        ))}
        <div className="contents" data-testid="tendance-ensemble">
          <div className="text-xs font-semibold text-emerald-300 leading-tight border-t border-slate-700 pt-2">
            Tout mis ensemble <span className="text-slate-500 font-normal">({fmtInt(t.matchs)} matchs)</span>
          </div>
          {tv.map((x, j) => (
            <div key={j} className={`border-t border-slate-700 pt-2 ${j === tk ? "text-emerald-300" : ""}`}>{cell(x, t.matchs)}</div>
          ))}
        </div>
      </div>
      <p className="mt-4 text-sm text-slate-200" data-testid="tendance-phrase">
        Tendance générale : <b className="text-emerald-300">{issueName(tk)}</b> ({fmt(100 * tv[tk] / t.matchs, 0)} % des matchs).{" "}
        <span className="text-slate-400">
          {rows.length > 1 && (accord
            ? `Les ${rows.length} sources vont dans le même sens.`
            : `Les sources ne sont pas d'accord : ${rows.map((r, i) => `${r.label.split(" à une cote")[0].replace("Tous les matchs à ces cotes", "les cotes")} → ${issueName(tops[i])}`).join(" ; ")}.`)}
        </span>
      </p>
      <ScoreChips scores={t.scores} label="Scores les plus fréquents, tout mis ensemble" testid="tendance-scores" />
      <p className="mt-2 text-[11px] text-slate-500">
        Chaque match n'est compté qu'une fois (score vu du côté de chaque équipe ici) ; pour une équipe, sa victoire compte pour son côté et sa défaite pour
        l'autre. Les matchs aux cotes voisines, bien plus nombreux, pèsent le plus.
        {test && <> Testée à l'aveugle sur {fmtInt(test.matchs)} matchs, cette tendance désigne la bonne issue aussi souvent
          que la cote seule ({fmt(test.reussite_pct)} % contre {fmt(test.reussite_cote_pct)} %), et parier quand elle trouve
          la cote trop haute rend <b className="text-red-400">{signed(test.roi_pct)}</b>.</>}
      </p>
    </div>
  );
}

const TYPE = { "avant-match": "avant le match", cloture: "à la clôture" };

// Fiche match : les matchs passés aux mêmes cotes que ce match (décompte, scores les
// plus fréquents, équipes et tendance), chargés à part pour ne pas ralentir la fiche.
export function MatchOddsHistory({ matchId }) {
  const [d, setD] = useState(undefined);
  useEffect(() => {
    setD(undefined);
    api.get(`/match/${matchId}/cotes-historiques`).then((r) => setD(r.data)).catch(() => setD(null));
  }, [matchId]);
  if (d === undefined) return null;
  if (!d?.disponible) {
    return (
      <div className="card-surface rounded-xl p-4 mb-6 text-xs text-slate-500" data-testid="match-odds-history-none">
        <b className="text-slate-300">Selon les cotes historiques</b> : pas encore de cotes pour ce match.
        football-data.co.uk les publie en fin de semaine pour les matchs du week-end, en début de semaine pour
        ceux du milieu de semaine.
      </div>
    );
  }
  const s = d.similaires;
  const cotes = [d.cotes.domicile, d.cotes.nul, d.cotes.exterieur];
  const q = new URLSearchParams({ domicile: cotes[0], nul: cotes[1], exterieur: cotes[2] });
  if (d.equipe_domicile?.trouvee) q.set("dom", d.equipe_domicile.nom);
  if (d.equipe_exterieur?.trouvee) q.set("ext", d.equipe_exterieur.nom);
  return (
    <div className="card-surface rounded-xl p-5 mb-6" data-testid="match-odds-history">
      <h2 className="font-head text-lg sm:text-xl font-bold text-slate-50 flex items-center gap-2">
        <History className="w-5 h-5 text-emerald-400" /> Selon les cotes historiques
      </h2>
      <p className="text-xs text-slate-500 mt-1 mb-3">
        Cotes {TYPE[d.source?.type] || ""} : <b className="font-stat text-slate-300">{cotes.map((c) => fmt(c, 2)).join(" / ")}</b>
        {d.source?.nom ? ` (${d.source.nom})` : ""}. Dans l'historique Pinnacle, <b className="text-slate-300">{fmtInt(s.matchs)} matchs</b>{" "}
        avaient à peu près les mêmes chances (± {s.precision_pct} % sur chaque cote, marge retirée) :
      </p>
      {s.matchs > 0 ? (
        <>
          <OutcomeCounts s={s} testid="match-odds-resume" />
          <ScoreChips scores={s.scores} testid="match-odds-scores" />
        </>
      ) : <p className="text-sm text-slate-400">Aucun match aussi proche dans l'historique.</p>}
      {d.tendance && <div className="mt-4"><Tendance d={d} nested /></div>}
      <Link to={`/cotes?${q}`} data-testid="match-odds-link"
        className="mt-3 inline-block text-xs text-emerald-400 hover:text-emerald-300">
        Tout le détail (exemples, rentabilité) sur la page Cotes →
      </Link>
    </div>
  );
}
