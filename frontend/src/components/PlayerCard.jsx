import { ScoreBadge } from "./ScoreBadge";
import { ScoreBar } from "./ScoreBar";
import { ScoreBreakdown } from "./ScoreBreakdown";

const Poste = ({ poste }) => (
  <span className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">{poste}</span>
);

export function PlayerRow({ player, rank, testid }) {
  const g = player.scores.global;
  const s = player.stats;
  return (
    <ScoreBreakdown data={g} title="Score joueur" team={player.nom} testid={testid}>
      <div className="card-surface rounded-xl p-3 flex items-center gap-3 cursor-pointer">
        {rank != null && <div className="w-6 text-center font-stat font-black text-slate-500">{rank}</div>}
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-slate-100 text-sm truncate">{player.nom}</div>
          <div className="flex items-center gap-2 mt-0.5">
            <Poste poste={player.poste} />
            <span className="text-[11px] text-slate-500 truncate">{player.team_title}</span>
          </div>
        </div>
        <div className="hidden sm:flex items-center gap-3 text-center shrink-0">
          <div><div className="font-stat font-bold text-emerald-400 text-sm">{s.buts}</div><div className="text-[9px] text-slate-500 uppercase">Buts</div></div>
          <div><div className="font-stat font-bold text-cyan-400 text-sm">{s.passes_decisives}</div><div className="text-[9px] text-slate-500 uppercase">PD</div></div>
          <div><div className="font-stat font-bold text-slate-300 text-sm">{s.xG}</div><div className="text-[9px] text-slate-500 uppercase">xG</div></div>
        </div>
        <ScoreBadge score={g.score} size="sm" />
      </div>
    </ScoreBreakdown>
  );
}

export function PlayerWatchCard({ player, side, testid }) {
  const s = player.stats;
  const slug = (player.nom || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return (
    <div className="card-surface rounded-xl p-4" data-testid={testid || `player-watch-card-${slug}`}>
      <div className="flex items-center gap-3 mb-3">
        <ScoreBreakdown data={player.scores.global} title="Score joueur" team={player.nom}>
          <button><ScoreBadge score={player.scores.global.score} /></button>
        </ScoreBreakdown>
        <div className="min-w-0">
          <div className="font-head font-bold text-slate-50 truncate">{player.nom}</div>
          <Poste poste={player.poste} />
        </div>
      </div>
      <div className="space-y-2">
        <ScoreBreakdown data={player.scores.buteur} title="Score buteur" team={player.nom}>
          <div><ScoreBar label="Buteur · détail" score={player.scores.buteur.score} /></div>
        </ScoreBreakdown>
        <ScoreBreakdown data={player.scores.creation} title="Score création" team={player.nom}>
          <div><ScoreBar label="Création · détail" score={player.scores.creation.score} /></div>
        </ScoreBreakdown>
        <ScoreBreakdown data={player.scores.forme} title="Implication (forme)" team={player.nom}>
          <div><ScoreBar label="Forme · détail" score={player.scores.forme.score} /></div>
        </ScoreBreakdown>
      </div>
      <div className="grid grid-cols-4 gap-1 mt-3 pt-3 border-t border-slate-800 text-center">
        <div><div className="font-stat font-bold text-emerald-400 text-sm">{s.buts}</div><div className="text-[9px] text-slate-500 uppercase">Buts</div></div>
        <div><div className="font-stat font-bold text-cyan-400 text-sm">{s.passes_decisives}</div><div className="text-[9px] text-slate-500 uppercase">P.D.</div></div>
        <div><div className="font-stat font-bold text-slate-300 text-sm">{s.tirs}</div><div className="text-[9px] text-slate-500 uppercase">Tirs</div></div>
        <div><div className="font-stat font-bold text-slate-300 text-sm">{s.matchs}</div><div className="text-[9px] text-slate-500 uppercase">Matchs</div></div>
      </div>
    </div>
  );
}
