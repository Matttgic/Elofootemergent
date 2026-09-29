import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { FormChips } from "./FormChips";
import { DataUnavailable } from "./DataUnavailable";
import { OddsLine, ValueBadge } from "./Probabilities";
import { ForecastNumbers, MODEL_NAME } from "./Forecast";
import { kickoff } from "../lib/format";
import { ChevronRight } from "lucide-react";

function TeamRow({ team, align = "left" }) {
  if (!team) return <div className="text-sm text-slate-500 py-2">Équipe inconnue</div>;
  const right = align === "right";
  return (
    <div className={`flex items-center gap-2.5 min-w-0 ${right ? "flex-row-reverse text-right" : ""}`}>
      {team.logo
        ? <img src={team.logo} alt="" className="w-8 h-8 object-contain shrink-0" />
        : <div className="w-8 h-8 rounded bg-slate-800 shrink-0" />}
      <div className="min-w-0">
        <div className="font-semibold text-sm text-slate-100 truncate">{team.nom_court || team.nom}</div>
        <div className={`mt-0.5 flex ${right ? "justify-end" : ""}`}><FormChips form={team.forme_recente} /></div>
      </div>
    </div>
  );
}

export function MatchCard({ match, index = 0 }) {
  const finished = match.status === "FINISHED";
  const inplay = ["IN_PLAY", "PAUSED"].includes(match.status);
  const h = match.domicile, a = match.exterieur;
  const pred = match.prediction;
  const testid = `match-card-${match.match_id}`;
  const homeName = h?.nom_court || match.home_team?.shortName || "Dom.";
  const awayName = a?.nom_court || match.away_team?.shortName || "Ext.";

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.4) }}
    >
      <Link to={`/match/${match.match_id}`} data-testid={testid}>
        <div className="card-surface rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold font-head">
              {match.competition?.nom} · J{match.matchday ?? "?"}
            </span>
            <span className={`text-[11px] font-stat px-2 py-0.5 rounded ${
              inplay ? "bg-emerald-500/20 text-emerald-400"
              : finished ? "bg-slate-800 text-slate-400"
              : "bg-cyan-500/15 text-cyan-300"}`}>
              {finished ? "Terminé" : inplay ? "En direct" : kickoff(match.utc_date)}
            </span>
          </div>

          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <TeamRow team={h} />
            <div className="flex flex-col items-center px-1">
              {finished
                ? <div className="font-stat font-black text-lg text-slate-100">
                    {match.score.home}<span className="text-slate-600 mx-1">-</span>{match.score.away}
                  </div>
                : <div className="text-xs text-slate-500 font-head font-bold">VS</div>}
            </div>
            <TeamRow team={a} align="right" />
          </div>

          {pred ? (
            <div className={`mt-4 rounded-lg px-3 py-2.5 border ${match.value ? "bg-amber-500/5 border-amber-500/40" : "bg-slate-900/40 border-slate-800"}`}
              data-testid={`${testid}-prediction`}>
              <div className="flex items-center justify-between mb-2 gap-2">
                <span className="text-[10px] uppercase tracking-wide text-slate-400 font-head font-semibold flex items-center gap-1.5">
                  {MODEL_NAME}{finished ? " · avant-match" : ""}
                  <ValueBadge value={match.value} testid={`${testid}-value-badge`} />
                </span>
                <span className="text-[10px] text-slate-500 font-stat" data-testid={`${testid}-elo`}
                  title="Notes Elo avant le match (domicile · extérieur)">
                  {pred.modele || "Elo"}
                </span>
              </div>
              <ForecastNumbers pred={pred} homeName={homeName} awayName={awayName} testid={`${testid}-probas`} />
              {match.cotes && (
                <div className="mt-2 pt-2 border-t border-slate-800/80">
                  <OddsLine cotes={match.cotes} value={match.value} testid={`${testid}-odds`} />
                </div>
              )}
              {!pred.fiable && (
                <div className="mt-1 text-[10px] text-slate-500">Notes encore peu fiables ({pred.matchs_min} matchs)</div>
              )}
            </div>
          ) : (
            <div className="mt-3 flex justify-center"><DataUnavailable label="Pronostic indisponible (historique manquant)" /></div>
          )}

          <div className="flex items-center justify-between mt-3 text-xs">
            <span className="text-slate-500" data-testid={`${testid}-form-notes`}
              title="Note de forme /100 : résumé des 10 derniers matchs du championnat (indicateur descriptif)">
              {h?.global != null && a?.global != null
                ? <>Forme /100 : <span className="font-stat text-slate-400">{h.global} · {a.global}</span></>
                : null}
            </span>
            <span className="flex items-center text-emerald-400 font-semibold">
              Analyse <ChevronRight className="w-3.5 h-3.5" />
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
