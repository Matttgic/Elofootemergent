import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { Skeleton } from "../components/ui/skeleton";
import { Coins, History, Search, ShieldAlert, Users } from "lucide-react";

const PRECISIONS = [3, 5, 10, 15];
const EXEMPLE = { domicile: "1.30", nul: "5.75", exterieur: "10.5", dom: "Paris SG", ext: "Marseille" };
const ISSUES = [["domicile", "1 · Domicile"], ["nul", "N · Nul"], ["exterieur", "2 · Extérieur"]];

const fmt = (v, d = 1) => (v == null ? "—" : Number(v).toFixed(d).replace(".", ","));
const fmtInt = (v) => (v == null ? "—" : Number(v).toLocaleString("fr-FR"));
const signed = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmt(v)} %`);
const gainColor = (v) => (v == null ? "text-slate-400" : v > 0 ? "text-emerald-400" : "text-red-400");
const parseOdd = (s) => {
  const v = parseFloat(String(s || "").replace(",", "."));
  return Number.isFinite(v) && v > 1 ? v : null;
};
const frDay = (iso) => iso.split("-").reverse().join("/");

function OddInput({ label, value, onChange, testid }) {
  return (
    <label className="block">
      <span className="text-[11px] text-slate-400">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} inputMode="decimal" placeholder="ex. 2,10"
        data-testid={testid}
        className="mt-1 w-full h-11 rounded-lg bg-slate-900/60 border border-slate-700 text-slate-100 text-lg font-stat text-center px-2 focus:outline-none focus:border-emerald-500" />
    </label>
  );
}

function TeamInput({ label, value, onChange, testid }) {
  return (
    <label className="block">
      <span className="text-[11px] text-slate-400">{label}</span>
      <input value={value} onChange={(e) => onChange(e.target.value)} list="cotes-equipes" placeholder="facultatif"
        data-testid={testid} autoComplete="off"
        className="mt-1 w-full h-10 rounded-lg bg-slate-900/60 border border-slate-700 text-slate-100 text-sm px-3 focus:outline-none focus:border-emerald-500" />
    </label>
  );
}

// Une issue : fréquence réelle des matchs comparables face à la probabilité annoncée par leurs cotes.
function IssueCell({ label, v, cote }) {
  return (
    <div className="rounded-lg bg-slate-900/50 p-3 text-center" data-testid="issue-cell">
      <div className="text-[11px] text-slate-400 mb-1">{label} · cote {fmt(cote, 2)}</div>
      <div className="font-stat font-black text-3xl text-slate-50 leading-none">{fmt(v.reel_pct, 0)}%</div>
      <div className="text-[10px] text-slate-500 mt-1">réel ({fmtInt(v.matchs)} matchs, ± {fmt(v.marge_erreur_pct)})</div>
      <div className="relative mt-2 h-1.5 rounded-full bg-slate-800 overflow-hidden">
        <div className="absolute inset-y-0 left-0 bg-emerald-500/80" style={{ width: `${v.reel_pct || 0}%` }} />
        <div className="absolute inset-y-0 w-0.5 bg-amber-300" style={{ left: `${v.annonce_pct || 0}%` }} title="annoncé par les cotes" />
      </div>
      <dl className="mt-2 space-y-0.5 text-[11px] text-left">
        <div className="flex justify-between"><dt className="text-slate-500">Annoncé par les cotes</dt><dd className="font-stat text-amber-300">{fmt(v.annonce_pct)} %</dd></div>
        <div className="flex justify-between"><dt className="text-slate-500">Rentable au-delà de</dt><dd className="font-stat text-slate-300">{fmt(v.seuil_pct)} %</dd></div>
        <div className="flex justify-between"><dt className="text-slate-500">Rendement à ta cote</dt><dd className={`font-stat font-bold ${gainColor(v.rendement_pct)}`}>{signed(v.rendement_pct)}</dd></div>
      </dl>
    </div>
  );
}

function Examples({ rows, testid }) {
  if (!rows?.length) return null;
  return (
    <details className="mt-3 group" data-testid={testid}>
      <summary className="cursor-pointer text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1">
        <History className="w-3.5 h-3.5" /> Les {rows.length} plus récents
      </summary>
      <div className="mt-2 space-y-1">
        <div className="grid grid-cols-[4.5rem_1fr_auto] gap-2 text-[10px] uppercase tracking-wide text-slate-600">
          <span>Date</span><span>Match</span><span>Cotes Pinnacle 1 / N / 2</span>
        </div>
        {rows.map((e, i) => (
          <div key={i} className="grid grid-cols-[4.5rem_1fr_auto] gap-2 items-center text-xs py-1 border-b border-slate-800 last:border-0">
            <span className="text-slate-500 font-stat">{frDay(e.date)}</span>
            <span className="text-slate-300 truncate">
              {e.domicile} <b className="font-stat text-slate-100">{e.score}</b> {e.exterieur}
              <span className="text-slate-600"> · {e.ligue}</span>
            </span>
            <span className="font-stat text-slate-500 whitespace-nowrap">{e.cotes.map((c) => fmt(c, 2)).join(" / ")}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

function TeamResult({ e, cote, testid }) {
  if (!e) return null;
  if (!e.trouvee) {
    return (
      <div className="card-surface rounded-xl p-4 text-sm text-slate-400" data-testid={testid}>
        <b className="text-slate-200">{e.nom}</b> : équipe absente de l'historique. Choisis un nom dans la liste
        (noms de football-data.co.uk, ex. « Paris SG », « Man City »).
      </div>
    );
  }
  return (
    <div className="card-surface rounded-xl p-5" data-testid={testid}>
      <h3 className="font-head font-bold text-slate-50">{e.nom} à une cote de victoire proche de {fmt(cote, 2)}</h3>
      <p className="text-xs text-slate-500 mt-0.5">
        {e.matchs
          ? <>{fmtInt(e.matchs)} matchs ({e.domicile} à domicile, {e.matchs - e.domicile} à l'extérieur), cotes de {fmt(e.cote_min, 2)} à {fmt(e.cote_max, 2)} · {e.ligues.join(", ")}</>
          : "Aucun match de cette équipe à une cote aussi proche : élargis la précision."}
      </p>
      {e.matchs > 0 && (
        <>
          <div className="grid grid-cols-3 gap-2 mt-3 text-center">
            {[["Victoire", e.victoire_pct, "text-emerald-300"], ["Nul", e.nul_pct, "text-slate-300"], ["Défaite", e.defaite_pct, "text-red-300"]].map(([l, v, c]) => (
              <div key={l} className="rounded-lg bg-slate-900/50 py-2">
                <div className={`font-stat font-black text-2xl ${c}`}>{fmt(v, 0)}%</div>
                <div className="text-[10px] text-slate-500">{l}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 text-xs text-slate-400 space-y-1">
            <div>Victoires annoncées par les cotes de ces matchs : <b className="text-amber-300 font-stat">{fmt(e.annonce_pct)} %</b>, réelles : <b className="text-slate-100 font-stat">{fmt(e.victoire_pct)} %</b> (± {fmt(e.marge_erreur_pct)}).</div>
            <div>Parier sa victoire à chaque fois aurait rendu <b className={`font-stat ${gainColor(e.roi_historique_pct)}`}>{signed(e.roi_historique_pct)}</b> ; à ta cote, cette réussite donnerait <b className={`font-stat ${gainColor(e.rendement_pct)}`}>{signed(e.rendement_pct)}</b>.</div>
          </div>
          {!e.suffisant && (
            <p className="mt-2 text-[11px] text-amber-400">Moins de 30 matchs : un ou deux résultats de plus changent tout, ce pourcentage ne veut presque rien dire.</p>
          )}
          <Examples rows={e.exemples} testid={`${testid}-exemples`} />
        </>
      )}
    </div>
  );
}

function Verdict({ t }) {
  if (!t) return null;
  return (
    <div className="card-surface rounded-xl p-5 border border-amber-500/30" data-testid="cotes-verdict">
      <h2 className="font-head text-lg font-bold text-slate-50 flex items-center gap-2 mb-2">
        <ShieldAlert className="w-5 h-5 text-amber-400" /> Et pour gagner de l'argent ?
      </h2>
      <p className="text-sm text-slate-300 mb-3">
        Testé à l'aveugle sur {fmtInt(t.matchs)} matchs ({t.saisons}) : chaque saison est jouée avec les seules
        saisons précédentes, comme si on pariait en direct.
      </p>
      <ul className="text-sm text-slate-400 space-y-2 list-disc pl-5">
        <li>
          <b className="text-slate-200">Les cotes disent déjà ce que dit l'historique.</b> Prévoir un match avec les
          matchs aux cotes voisines ne fait pas mieux que la cote elle-même (log-loss {fmt(t.logloss_similaires, 4)} contre {fmt(t.logloss_pinnacle, 4)} ; plus c'est bas, mieux c'est).
        </li>
        <li>
          Parier quand l'historique dit que la cote est trop haute : {fmtInt(t.paris_similaires.paris)} paris,{" "}
          <b className="text-red-400">{signed(t.paris_similaires.roi_pct)}</b> ; seulement quand l'écart dépasse 5 % :{" "}
          <b className="text-red-400">{signed(t.paris_similaires_5.roi_pct)}</b> (parier tout, au hasard : {signed(t.marge_roi_pct)}).
        </li>
        <li>
          <b className="text-slate-200">Les équipes n'ont pas de « chance » durable.</b> Une équipe qui a battu ses
          cotes une saison ne le fait pas plus la suivante (corrélation {fmt(t.correlation_equipes, 3)} sur{" "}
          {fmtInt(t.equipes_saisons)} équipes-saisons) ; parier d'après son historique à cote proche :{" "}
          <b className="text-red-400">{signed(t.paris_equipes.roi_pct)}</b>.
        </li>
        <li>
          Rejouer les tranches de cotes rentables par le passé (gros favoris…) la saison suivante :{" "}
          <b className="text-red-400">{signed(t.zones.roi_pct)}</b> sur {fmtInt(t.zones.paris)} paris.
        </li>
        <li>
          Tout combiner, avec des poids réglés sur les saisons passées : le poids donné à l'historique ressort à{" "}
          {t.combinaison.poids} chaque saison, la combinaison revient à la cote seule (log-loss {fmt(t.combinaison.logloss, 4)}).
        </li>
        <li>
          Ces rendements sont aux cotes Pinnacle (marge ≈ 3 %) : chez un bookmaker français (marge 6 à 10 %), ils
          sont encore 3 à 7 points plus bas.
        </li>
      </ul>
    </div>
  );
}

function Calibration({ cal }) {
  const [issue, setIssue] = useState("domicile");
  if (!cal) return null;
  return (
    <div className="card-surface rounded-xl p-5" data-testid="cotes-calibration">
      <h2 className="font-head text-lg font-bold text-slate-50 mb-1">Toutes les cotes : annoncé ou réel ?</h2>
      <p className="text-xs text-slate-500 mb-3">
        Tout l'historique par tranche de cote Pinnacle : la probabilité que donnait la cote (sans marge), ce qui
        s'est vraiment passé, et le rendement si l'on avait parié cette issue à chaque fois. Seuls les très gros
        favoris frôlent l'équilibre ; les grosses cotes perdent beaucoup.
      </p>
      <div className="flex gap-1 mb-3">
        {ISSUES.map(([k, l]) => (
          <button key={k} onClick={() => setIssue(k)} data-testid={`calibration-${k}`}
            className={`px-3 py-1 rounded-lg text-xs ${issue === k ? "bg-emerald-500/15 text-emerald-300" : "text-slate-400 hover:text-slate-200"}`}>
            {l}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs sm:text-sm">
          <thead>
            <tr className="text-left text-[11px] text-slate-500 border-b border-slate-800">
              <th className="py-1.5 pr-2">Cote</th>
              <th className="py-1.5 px-2 text-right hidden sm:table-cell">Matchs</th>
              <th className="py-1.5 px-2 text-right">Annoncé</th>
              <th className="py-1.5 px-2 text-right">Réel</th>
              <th className="py-1.5 pl-2 text-right">Rendement</th>
            </tr>
          </thead>
          <tbody>
            {cal[issue].map((r) => (
              <tr key={r.cote_min} className="border-b border-slate-800/60">
                <td className="py-1.5 pr-2 font-stat text-slate-300 whitespace-nowrap">{r.cote_max ? `${fmt(r.cote_min, 2)}–${fmt(r.cote_max, 2)}` : `${fmt(r.cote_min, 0)} et +`}</td>
                <td className="py-1.5 px-2 text-right font-stat text-slate-500 hidden sm:table-cell">{fmtInt(r.matchs)}</td>
                <td className="py-1.5 px-1 sm:px-2 text-right font-stat text-amber-300 whitespace-nowrap">{fmt(r.annonce_pct)} %</td>
                <td className="py-1.5 px-1 sm:px-2 text-right font-stat text-slate-100 whitespace-nowrap">{fmt(r.reel_pct)} %</td>
                <td className={`py-1.5 pl-1 sm:pl-2 text-right font-stat whitespace-nowrap ${gainColor(r.roi_pct)}`}>{signed(r.roi_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Cotes() {
  const [params, setParams] = useSearchParams();
  const [form, setForm] = useState(() => ({
    domicile: params.get("domicile") || "", nul: params.get("nul") || "", exterieur: params.get("exterieur") || "",
    dom: params.get("dom") || "", ext: params.get("ext") || "",
  }));
  const precision = Number(params.get("precision")) || 5;
  const [teams, setTeams] = useState([]);
  const [meta, setMeta] = useState(null);
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/cotes/equipes").then((r) => setTeams(r.data.equipes)).catch(() => setTeams([]));
    api.get("/cotes/calibration").then((r) => setMeta(r.data)).catch(() => setMeta(null));
  }, []);

  const [qd, qn, qe, qdom, qext] = ["domicile", "nul", "exterieur", "dom", "ext"].map((k) => params.get(k) || "");

  useEffect(() => {
    const [domicile, nul, exterieur] = [qd, qn, qe].map(parseOdd);
    if (!(domicile && nul && exterieur)) { setD(null); return; }
    setLoading(true);
    setError(null);
    api.get("/cotes/similaires", {
      params: { domicile, nul, exterieur, precision, equipe_domicile: qdom || undefined, equipe_exterieur: qext || undefined },
    }).then((r) => setD(r.data))
      .catch((e) => { setD(null); setError(typeof e.response?.data?.detail === "string" ? e.response.data.detail : "Cotes invalides."); })
      .finally(() => setLoading(false));
  }, [qd, qn, qe, qdom, qext, precision]);

  const submit = (next = form) => {
    const odds = [next.domicile, next.nul, next.exterieur].map(parseOdd);
    if (odds.some((o) => !o)) { setError("Entre les trois cotes 1, N et 2 (nombres supérieurs à 1)."); return; }
    const p = { domicile: String(odds[0]), nul: String(odds[1]), exterieur: String(odds[2]), precision: String(precision) };
    if (next.dom.trim()) p.dom = next.dom.trim();
    if (next.ext.trim()) p.ext = next.ext.trim();
    setParams(p);
  };
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const s = d?.similaires;
  const h = d?.historique || meta?.historique;

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1 flex items-center gap-2">
        <Coins className="w-7 h-7 text-emerald-400" /> Cotes similaires
      </h1>
      <p className="text-slate-400 text-sm mb-5">
        Entre les cotes 1N2 d'un match : on retrouve les matchs passés où les cotes Pinnacle étaient proches et on
        regarde comment ils ont fini
        {h ? <> ({fmtInt(h.matchs)} matchs, {h.championnats} championnats, {h.debut.slice(0, 4)} à {h.fin.slice(0, 4)})</> : null}.
        Avec deux équipes, on regarde aussi leurs propres matchs à une cote de victoire proche.
      </p>

      <form className="card-surface rounded-xl p-4 sm:p-5 mb-5 space-y-3" data-testid="cotes-form"
        onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <div className="grid grid-cols-3 gap-2 sm:gap-3">
          <OddInput label="1 · Domicile" value={form.domicile} onChange={set("domicile")} testid="cote-domicile" />
          <OddInput label="N · Nul" value={form.nul} onChange={set("nul")} testid="cote-nul" />
          <OddInput label="2 · Extérieur" value={form.exterieur} onChange={set("exterieur")} testid="cote-exterieur" />
        </div>
        <div className="grid grid-cols-2 gap-2 sm:gap-3">
          <TeamInput label="Équipe à domicile" value={form.dom} onChange={set("dom")} testid="equipe-domicile" />
          <TeamInput label="Équipe à l'extérieur" value={form.ext} onChange={set("ext")} testid="equipe-exterieur" />
          <datalist id="cotes-equipes">
            {teams.map((t) => <option key={t.nom} value={t.nom}>{t.ligues.join(", ")}</option>)}
          </datalist>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] text-slate-400">Cotes proches à</span>
          {PRECISIONS.map((p) => (
            <button type="button" key={p} data-testid={`precision-${p}`}
              onClick={() => setParams({ ...Object.fromEntries(params), precision: String(p) })}
              className={`px-2.5 py-1 rounded-lg text-xs font-stat ${precision === p ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40" : "bg-slate-800/60 text-slate-400 hover:text-slate-200"}`}>
              ± {p} %
            </button>
          ))}
          <button type="submit" data-testid="cotes-submit"
            className="ml-auto inline-flex items-center gap-1.5 h-10 px-4 rounded-lg bg-emerald-500 text-slate-950 font-semibold text-sm hover:bg-emerald-400">
            <Search className="w-4 h-4" /> Chercher
          </button>
        </div>
        <button type="button" className="text-[11px] text-slate-500 hover:text-emerald-400" data-testid="cotes-exemple"
          onClick={() => { setForm(EXEMPLE); submit(EXEMPLE); }}>
          Exemple : Paris SG – Marseille à 1,30 / 5,75 / 10,5
        </button>
        {error && <p className="text-sm text-red-400" data-testid="cotes-error">{error}</p>}
      </form>

      {loading && <div className="space-y-3 mb-5"><Skeleton className="h-48 rounded-xl bg-slate-800/50" /></div>}

      {d && !loading && (
        <div className="space-y-4 mb-6" data-testid="cotes-result">
          <div className="card-surface rounded-xl p-5 border border-emerald-500/20" data-testid="cotes-similaires">
            <h2 className="font-head text-xl font-bold text-slate-50">
              {fmtInt(s.matchs)} matchs avec ces cotes
            </h2>
            <p className="text-xs text-slate-500 mt-0.5 mb-3">
              Matchs passés où les cotes Pinnacle étaient à ± {s.precision_pct} % des tiennes
              {s.identiques ? <> (dont {s.identiques} aux cotes exactement identiques)</> : null}.
            </p>
            {s.matchs > 0 ? (
              <>
                <div className="grid grid-cols-3 gap-2 text-center" data-testid="cotes-resume">
                  {[["domicile", "Victoire à domicile", "text-emerald-300"], ["nul", "Match nul", "text-slate-200"],
                    ["exterieur", "Victoire à l'extérieur", "text-cyan-300"]].map(([k, l, c]) => (
                    <div key={k} className="rounded-lg bg-slate-900/60 py-3 px-1" data-testid={`resume-${k}`}>
                      <div className={`font-stat font-black text-3xl sm:text-4xl leading-none ${c}`}>{fmtInt(s.issues[k].matchs)}</div>
                      <div className="text-[11px] text-slate-300 mt-1.5">{l}</div>
                      <div className="font-stat text-sm text-slate-400 mt-0.5">{fmt(s.issues[k].reel_pct, 0)} %</div>
                    </div>
                  ))}
                </div>
                {d.marge_pct > 5 && s.cotes_pinnacle && (
                  <p className="text-[11px] text-slate-400 mt-3" data-testid="cotes-equivalent">
                    Tes cotes {[d.cotes.domicile, d.cotes.nul, d.cotes.exterieur].map((c) => fmt(c, 2)).join(" / ")} contiennent{" "}
                    <b className="text-amber-300">{fmt(d.marge_pct)} % de marge</b> (Pinnacle ≈ 3 %). Pour les mêmes chances,
                    Pinnacle affichait ≈ <b className="text-slate-200 font-stat">{s.cotes_pinnacle.map((c) => fmt(c, 2)).join(" / ")}</b> :
                    ce sont ces matchs-là qui sont comptés (aucun match Pinnacle n'a des cotes aussi basses sur les trois issues).
                  </p>
                )}
                {!s.suffisant && <p className="mt-2 text-[11px] text-amber-400">Moins de 30 matchs : élargis la précision, un ou deux résultats de plus changent tout.</p>}
                <Examples rows={s.exemples} testid="similaires-exemples" />
                <details className="mt-3" data-testid="similaires-details">
                  <summary className="cursor-pointer text-xs text-emerald-400 hover:text-emerald-300">
                    Rentable ou pas ? Détail par issue
                  </summary>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
                    {ISSUES.map(([k, l]) => <IssueCell key={k} label={l} v={s.issues[k]} cote={d.cotes[k]} />)}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-3">
                    <span className="inline-block w-2 h-2 bg-emerald-500/80 rounded-sm mr-1" />réel
                    <span className="inline-block w-0.5 h-2.5 bg-amber-300 mx-1 ml-3 align-middle" />annoncé par les cotes.
                    « Rendement à ta cote » : ce que rapporterait un pari de 1 € si la fréquence passée se répétait
                    exactement (± la marge d'erreur, qui suffit souvent à changer le signe).
                  </p>
                </details>
              </>
            ) : (
              <p className="text-sm text-slate-400">Aucun match aussi proche : élargis la précision.</p>
            )}
          </div>

          {(d.equipe_domicile || d.equipe_exterieur) && (
            <div className="space-y-3">
              <h2 className="font-head text-lg font-bold text-slate-50 flex items-center gap-2">
                <Users className="w-5 h-5 text-emerald-400" /> Les équipes à cette cote
              </h2>
              <TeamResult e={d.equipe_domicile} cote={d.cotes.domicile} testid="equipe-domicile-result" />
              <TeamResult e={d.equipe_exterieur} cote={d.cotes.exterieur} testid="equipe-exterieur-result" />
            </div>
          )}
        </div>
      )}

      <div className="space-y-4">
        <Verdict t={meta?.test} />
        <Calibration cal={meta?.calibration} />
        <p className="text-[11px] text-slate-600">
          Source : football-data.co.uk, cotes Pinnacle à la clôture (juste avant le coup d'envoi), 2012 à début 2026 ;
          le site ne les publie plus depuis. Les cotes d'un autre bookmaker sont comparées après retrait de sa marge.
        </p>
      </div>
    </div>
  );
}
