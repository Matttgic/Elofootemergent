import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ScoreBadge } from "./ScoreBadge";
import { ScoreBar } from "./ScoreBar";
import { FormChips } from "./FormChips";
import { DataUnavailable } from "./DataUnavailable";
import { ProbabilityBar, OddsLine, ValueBadge } from "./Probabilities";
import { kickoff } from "../lib/format";
import { ChevronRight } from "lucide-react";

function TeamRow({ team, side }) {
  if (!team) return <div className="text-sm text-slate-500 py-2">Équipe inconnue</div>;
  return (
    <div className="flex items-center gap-3 min-w-0">
      {team.logo
        ? <img src={team.logo} alt="" className="w-8 h-8 object-contain shrink-0" />
        : <div className="w-8 h-8 rounded bg-slate-800 shrink-0" />}
      <div className="min-w-0">
        <div className="font-semibold text-sm text-slate-100 truncate">{team.nom_court || team.nom}</div>
        <div className="mt-0.5"><FormChips form={team.forme_recente} /></div>
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
            <TeamRow team={h} side="home" />
            <div className="flex flex-col items-center px-1">
              {finished
                ? <div className="font-stat font-black text-lg text-slate-100">
                    {match.score.home}<span className="text-slate-600 mx-1">-</span>{match.score.away}
                  </div>
                : <div className="text-xs text-slate-500 font-head font-bold">VS</div>}
            </div>
            <div className="flex justify-end"><TeamRow team={a} side="away" /></div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-4">
            <div className="flex items-center gap-2">
              <ScoreBadge score={h?.global} size="sm" testid={`${testid}-home-global`} />
              <span className="text-[10px] text-slate-500 uppercase font-head">Global<br/>Domicile</span>
            </div>
            <div className="flex items-center gap-2 justify-end">
              <span className="text-[10px] text-slate-500 uppercase font-head text-right">Global<br/>Extérieur</span>
              <ScoreBadge score={a?.global} size="sm" testid={`${testid}-away-global`} />
            </div>
          </div>

          {pred && (
            <div className={`mt-3 rounded-lg px-3 py-2 border ${match.value ? "bg-amber-500/10 border-amber-500/40" : "bg-slate-800/40 border-slate-800"}`} data-testid={`${testid}-prediction`}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 font-head flex items-center gap-1.5">
                  {finished ? "Probabilités avant-match" : "Probabilités"} · {pred.modele || "Elo"}
                  <ValueBadge value={match.value} testid={`${testid}-value-badge`} />
                </span>
                <span className="text-[11px] font-stat text-slate-400" data-testid={`${testid}-elo`}
                  title="Notes Elo (domicile · extérieur)">
                  {pred.elo_domicile} · {pred.elo_exterieur}
                </span>
              </div>
              <ProbabilityBar pred={pred} homeName={h?.nom_court || "Dom."} awayName={a?.nom_court || "Ext."}
                testid={`${testid}-probas`} />
              {match.cotes && (
                <div className="mt-1.5 pt-1.5 border-t border-slate-800/80">
                  <OddsLine cotes={match.cotes} value={match.value} testid={`${testid}-odds`} />
                </div>
              )}
              {!pred.fiable && (
                <div className="mt-1 text-[10px] text-slate-500">Notes encore peu fiables ({pred.matchs_min} matchs)</div>
              )}
            </div>
          )}

          {(h || a) && (
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 mt-4 pt-3 border-t border-slate-800">
              <div className="space-y-1.5">
                <ScoreBar label="Attaque" score={h?.offensif} />
                <ScoreBar label="Défense" score={h?.defensif} />
                <ScoreBar label="Forme" score={h?.forme} />
              </div>
              <div className="space-y-1.5">
                <ScoreBar label="Attaque" score={a?.offensif} />
                <ScoreBar label="Défense" score={a?.defensif} />
                <ScoreBar label="Forme" score={a?.forme} />
              </div>
            </div>
          )}

          {!h && !a && (
            <div className="mt-3 flex justify-center"><DataUnavailable label="Analyse indisponible (historique manquant)" /></div>
          )}

          <div className="flex items-center justify-end mt-3 text-emerald-400 text-xs font-semibold">
            Analyse détaillée <ChevronRight className="w-3.5 h-3.5" />
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
