import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { ScoreBadge } from "../components/ScoreBadge";
import { ScoreBar } from "../components/ScoreBar";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { DataUnavailable } from "../components/DataUnavailable";
import { TeamLogo } from "../components/TeamLogo";
import { Skeleton } from "../components/ui/skeleton";
import { frDate, resultColor } from "../lib/format";
import { ArrowLeft } from "lucide-react";

export default function PlayerPage() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/player/${id}`).then((r) => setP(r.data)).catch(() => setP(null)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-6 space-y-4"><Skeleton className="h-32 rounded-xl bg-slate-800/50" /><Skeleton className="h-48 rounded-xl bg-slate-800/50" /></div>;
  if (!p) return <div className="max-w-3xl mx-auto px-4 py-10 text-center text-slate-400">Joueur introuvable.</div>;

  const s = p.stats;
  const forme = p.forme_recente;

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-6">
      <Link to="/classements" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-emerald-400 mb-4">
        <ArrowLeft className="w-4 h-4" /> Retour
      </Link>

      <div className="card-surface rounded-xl p-5 mb-4 flex items-center gap-4" data-testid="player-header">
        <ScoreBreakdown data={p.scores.global} title="Score joueur" team={p.nom}>
          <button><ScoreBadge score={p.scores.global.score} size="lg" /></button>
        </ScoreBreakdown>
        <div className="min-w-0">
          <h1 className="font-head text-2xl font-extrabold text-slate-50 truncate">{p.nom}</h1>
          <div className="text-sm text-slate-400 flex items-center gap-1.5 flex-wrap">
            <span>{p.poste} ·</span>
            <TeamLogo src={p.team_logo} className="w-5 h-5" />
            <span>{p.team_title} · {p.competition_nom}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {[["buteur", "Buteur"], ["creation", "Création"], ["offensif", "Offensif"], ["forme", "Implication"]].map(([k, label]) => (
          <div key={k} className="card-surface rounded-xl p-4">
            <ScoreBreakdown data={p.scores[k]} title={label} team={p.nom}>
              <div><ScoreBar label={`${label} · détail`} score={p.scores[k]?.score} /></div>
            </ScoreBreakdown>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-4 sm:grid-cols-7 gap-2 mb-4">
        {[["Matchs", s.matchs], ["Min", s.minutes], ["Buts", s.buts], ["P.D.", s.passes_decisives],
          ["Tirs", s.tirs], ["xG", s.xG], ["xA", s.xA]].map(([l, v]) => (
          <div key={l} className="card-surface rounded-lg p-2 text-center">
            <div className="font-stat font-bold text-slate-100 text-sm">{v}</div>
            <div className="text-[9px] text-slate-500 uppercase">{l}</div>
          </div>
        ))}
      </div>

      <h3 className="font-head font-bold text-slate-100 mb-2">Forme récente</h3>
      {forme?.form_score ? (
        <div className="card-surface rounded-xl p-4" data-testid="player-recent-form">
          <div className="flex items-center gap-3 mb-3">
            <ScoreBreakdown data={forme.form_score} title="Forme récente" team={p.nom}>
              <button><ScoreBadge score={forme.form_score.score} /></button>
            </ScoreBreakdown>
            <div className="text-sm text-slate-300">
              <b className="text-emerald-400 font-stat">{forme.resume.buts}</b> buts et
              <b className="text-cyan-400 font-stat"> {forme.resume.passes}</b> passes sur {forme.resume.matchs} matchs
            </div>
          </div>
          <div className="space-y-1.5">
            {forme.matchs.map((mt, i) => (
              <div key={i} className="flex items-center gap-2 text-sm py-1 border-b border-slate-800 last:border-0">
                <span className="w-16 text-xs text-slate-500 shrink-0">{frDate(mt.date)}</span>
                {mt.resultat && <span className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold text-white shrink-0" style={{ backgroundColor: resultColor(mt.resultat) }}>{mt.resultat === "W" ? "V" : mt.resultat === "D" ? "N" : "D"}</span>}
                <span className="text-slate-500 text-xs w-10 shrink-0">{mt.lieu === "Domicile" ? "Dom." : mt.lieu === "Extérieur" ? "Ext." : ""}</span>
                <span className="text-slate-200 flex-1 truncate">{mt.adversaire}</span>
                <span className="font-stat text-emerald-400 text-xs">{mt.buts} B</span>
                <span className="font-stat text-cyan-400 text-xs">{mt.passes} PD</span>
              </div>
            ))}
          </div>
        </div>
      ) : <DataUnavailable label="Forme récente indisponible" />}
    </div>
  );
}
