import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { frDate, kickoff } from "../lib/format";
import { TeamLogo } from "./TeamLogo";
import { ListChecks, Zap } from "lucide-react";

const ISSUE = { domicile: "1", nul: "N", exterieur: "2" };
const odds = (v) => (typeof v === "number" ? v.toFixed(2) : "—");
const STATUT = {
  won: ["Gagné", "bg-emerald-500/15 text-emerald-400"],
  lost: ["Perdu", "bg-red-500/15 text-red-400"],
  void: ["Annulé", "bg-slate-700/60 text-slate-400"],
  pending: ["En attente", "bg-cyan-500/15 text-cyan-300"],
};

function Clv({ v }) {
  if (v === null || v === undefined) return null;
  return (
    <span className={`font-stat ${v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-slate-400"}`}
      title="Valeur de clôture : cote obtenue comparée à la dernière cote relevée avant le match">
      CLV {v > 0 ? "+" : ""}{v}%
    </span>
  );
}

// Paris suivis par la simulation : à venir ou déjà réglés.
export function BetsList() {
  const [statut, setStatut] = useState("en_attente");
  const [data, setData] = useState({});

  useEffect(() => {
    if (data[statut]) return;
    api.get("/bets", { params: { statut, limit: 40 } })
      .then((r) => setData((d) => ({ ...d, [statut]: r.data.paris })))
      .catch(() => setData((d) => ({ ...d, [statut]: [] })));
  }, [statut, data]);

  const rows = data[statut];
  return (
    <div className="card-surface rounded-xl p-5 mt-4" data-testid="bets-list">
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2">
          <ListChecks className="w-5 h-5 text-cyan-400" />
          <h3 className="font-head font-bold text-slate-100">Paris suivis</h3>
        </div>
        <div className="flex gap-2">
          {[["en_attente", "À venir"], ["regles", "Réglés"]].map(([k, l]) => (
            <button key={k} onClick={() => setStatut(k)} data-testid={`bets-tab-${k}`}
              className={`px-3 py-1 rounded-full text-xs font-medium ${statut === k ? "bg-cyan-500 text-white" : "bg-slate-800/60 text-slate-400"}`}>{l}</button>
          ))}
        </div>
      </div>
      {!rows ? (
        <div className="text-sm text-slate-500 py-4 text-center">Chargement…</div>
      ) : rows.length === 0 ? (
        <div className="text-sm text-slate-500 py-4 text-center">Aucun pari {statut === "en_attente" ? "à venir" : "réglé"} pour le moment.</div>
      ) : (
        <div className="divide-y divide-slate-800" data-testid={`bets-rows-${statut}`}>
          {rows.map((b) => {
            const [label, cls] = STATUT[b.statut] || STATUT.pending;
            const played = b.score && b.score.home !== null && b.score.home !== undefined;
            return (
              <Link key={b.match_id} to={`/match/${b.match_id}`} className="block py-2.5 hover:bg-slate-800/30 -mx-2 px-2 rounded"
                data-testid={`bet-row-${b.match_id}`}>
                <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                  <span>{frDate(b.date)} · {kickoff(b.date)}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${cls}`}>{label}</span>
                </div>
                <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm mt-1">
                  <span className="flex items-center gap-1.5 min-w-0">
                    <TeamLogo src={b.domicile.logo} />
                    <span className="text-slate-200 truncate">{b.domicile.nom}</span>
                  </span>
                  <span className="font-stat text-slate-300">{played ? `${b.score.home}-${b.score.away}` : "–"}</span>
                  <span className="flex items-center gap-1.5 min-w-0 justify-end">
                    <span className="text-slate-200 truncate">{b.exterieur.nom}</span>
                    <TeamLogo src={b.exterieur.logo} />
                  </span>
                </div>
                <div className="flex items-center gap-x-3 gap-y-0.5 mt-1 text-[11px] text-slate-400 flex-wrap">
                  <span>
                    Favori <b className="text-slate-200">{ISSUE[b.favori.issue]}</b> @ <span className="font-stat">{odds(b.favori.cote)}</span>
                    <span className="text-slate-500"> ({b.favori.proba_pct}%)</span>
                  </span>
                  <Clv v={b.favori.clv_pct} />
                  {b.value && (
                    <span className="inline-flex items-center gap-1 text-amber-400">
                      <Zap className="w-3 h-3 fill-amber-400" /> Value {ISSUE[b.value.issue]} @ <span className="font-stat">{odds(b.value.cote)}</span>
                      <span className="text-amber-400/70">(+{b.value.avantage_pct}%)</span>
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
