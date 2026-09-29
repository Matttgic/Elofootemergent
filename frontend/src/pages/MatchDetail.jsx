import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { ScoreBadge } from "../components/ScoreBadge";
import { ScoreBar } from "../components/ScoreBar";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { MarketSignals } from "../components/MarketSignals";
import { PlayerWatchCard } from "../components/PlayerCard";
import { DataUnavailable } from "../components/DataUnavailable";
import { FormChips } from "../components/FormChips";
import { OddsLine, ValueBadge } from "../components/Probabilities";
import { frDate, kickoff, scoreColor } from "../lib/format";
import { Skeleton } from "../components/ui/skeleton";
import { ArrowLeft, Trophy, Users, History, Swords } from "lucide-react";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend,
} from "recharts";

function TeamPanel({ team, side, code }) {
  if (!team) {
    return <div className="card-surface rounded-xl p-5"><DataUnavailable label="Analyse indisponible" /></div>;
  }
  const scores = [
    { key: "global", label: "Score global", data: team.global },
    { key: "offensif", label: "Attaque", data: team.offensif },
    { key: "defensif", label: "Défense", data: team.defensif },
    { key: "forme", label: "Forme", data: team.forme },
  ];
  return (
    <div className="card-surface rounded-xl p-5" data-testid={`team-panel-${side}`}>
      <div className="flex items-center gap-3 mb-4">
        {team.logo ? <img src={team.logo} alt="" className="w-12 h-12 object-contain" />
          : <div className="w-12 h-12 rounded bg-slate-800" />}
        <div className="min-w-0">
          <Link to={`/equipe/${code}/${team.team_id}`} data-testid={`team-link-${side}`}
            className="font-head font-bold text-lg text-slate-50 truncate block hover:text-emerald-400">
            {team.nom}
          </Link>
          <div className="flex items-center gap-2 mt-1">
            <FormChips form={team.stats?.forme_recente} />
            {team.classement && (
              <span className="text-xs text-slate-500 font-stat">#{team.classement.position}</span>
            )}
            {team.elo && (
              <span className="text-xs text-slate-400 font-stat" data-testid={`team-elo-${side}`}
                title={team.elo.rang ? `${team.elo.rang}e Elo sur ${team.elo.sur} en ${team.elo.championnat_nom || team.elo.championnat}` : "Note Elo"}>
                Elo <b className="text-slate-200">{team.elo.elo}</b>
              </span>
            )}
          </div>
        </div>
        <div className="ml-auto">
          <ScoreBreakdown data={team.global} title="Score global" team={team.nom_court}
            testid={`score-breakdown-global-${side}`}>
            <button><ScoreBadge score={team.global?.score} size="lg" /></button>
          </ScoreBreakdown>
        </div>
      </div>

      <div className="space-y-2.5">
        {scores.slice(1).map((s) => (
          <ScoreBreakdown key={s.key} data={s.data} title={s.label} team={team.nom_court}
            testid={`score-breakdown-${s.key}-${side}`}>
            <div><ScoreBar label={`${s.label} · voir le détail`} score={s.data?.score} /></div>
          </ScoreBreakdown>
        ))}
      </div>

      {team.stats && (
        <div className="grid grid-cols-3 gap-2 mt-4 pt-4 border-t border-slate-800 text-center">
          <div><div className="font-stat font-bold text-emerald-400">{team.stats.buts_marques}</div><div className="text-[10px] text-slate-500 uppercase">Buts</div></div>
          <div><div className="font-stat font-bold text-red-400">{team.stats.buts_encaisses}</div><div className="text-[10px] text-slate-500 uppercase">Encaissés</div></div>
          <div><div className="font-stat font-bold text-slate-200">{team.stats.difference > 0 ? "+" : ""}{team.stats.difference}</div><div className="text-[10px] text-slate-500 uppercase">Diff.</div></div>
        </div>
      )}
    </div>
  );
}

function VenueSplit({ home, away }) {
  const Row = ({ label, score }) => (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-slate-400">{label}</span>
      {score === null || score === undefined
        ? <DataUnavailable />
        : <span className="font-stat font-bold text-sm" style={{ color: scoreColor(score) }}>{score}</span>}
    </div>
  );
  return (
    <div className="card-surface rounded-xl p-5">
      <h3 className="font-head font-bold text-slate-100 mb-2">Domicile vs Extérieur</h3>
      <div className="grid grid-cols-2 gap-6">
        <div>
          <div className="text-xs text-emerald-400 font-semibold mb-1">{home?.nom_court} · à domicile</div>
          <Row label="Score domicile" score={home?.domicile?.score} />
        </div>
        <div>
          <div className="text-xs text-cyan-400 font-semibold mb-1">{away?.nom_court} · à l'extérieur</div>
          <Row label="Score extérieur" score={away?.exterieur?.score} />
        </div>
      </div>
    </div>
  );
}

export default function MatchDetail() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [formMap, setFormMap] = useState({});

  useEffect(() => {
    setLoading(true);
    setFormMap({});
    api.get(`/match/${id}`).then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!d?.joueurs?.disponible) return;
    const ids = [...(d.joueurs.domicile || []), ...(d.joueurs.exterieur || [])].map((p) => p.player_id);
    if (!ids.length) return;
    api.post("/players/form", { ids }).then((r) => setFormMap(r.data || {})).catch(() => {});
  }, [d]);

  if (loading) return <div className="max-w-5xl mx-auto px-4 py-6 space-y-4"><Skeleton className="h-40 rounded-xl bg-slate-800/50" /><Skeleton className="h-64 rounded-xl bg-slate-800/50" /></div>;
  if (!d) return <div className="max-w-5xl mx-auto px-4 py-10 text-center text-slate-400">Match introuvable.</div>;

  const m = d.match, home = d.domicile, away = d.exterieur;
  const finished = m.status === "FINISHED";

  const radarData = ["global", "offensif", "defensif", "forme"].map((k) => ({
    stat: { global: "Global", offensif: "Attaque", defensif: "Défense", forme: "Forme" }[k],
    dom: home?.[k]?.score ?? 0,
    ext: away?.[k]?.score ?? 0,
  }));

  const advLabel = { global: "Avantage global", offensif: "Avantage offensif", defensif: "Avantage défensif", forme: "Forme" };

  return (
    <div className="max-w-5xl mx-auto px-3 sm:px-6 py-6">
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-emerald-400 mb-4" data-testid="back-link">
        <ArrowLeft className="w-4 h-4" /> Retour
      </Link>

      {/* Match header */}
      <div className="card-surface rounded-xl p-5 mb-6 fade-up">
        <div className="flex items-center justify-center gap-1.5 text-xs text-slate-500 mb-3 font-head uppercase tracking-wider">
          <Trophy className="w-3.5 h-3.5" /> {m.competition?.nom} · {m.competition?.pays} · J{m.matchday ?? "?"}
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <div className="flex flex-col items-center text-center gap-2">
            {m.home_team?.crest && <img src={m.home_team.crest} alt="" className="w-14 h-14 sm:w-16 sm:h-16 object-contain" />}
            <div className="font-head font-bold text-slate-50 text-sm sm:text-base">{m.home_team?.shortName || m.home_team?.name}</div>
          </div>
          <div className="text-center">
            {finished
              ? <div className="font-stat font-black text-3xl sm:text-4xl text-slate-50">{m.score.home}<span className="text-slate-600 mx-2">-</span>{m.score.away}</div>
              : <div className="font-head font-bold text-slate-300 text-lg">{kickoff(m.utc_date)}</div>}
            <div className="text-xs text-slate-500 mt-1">{frDate(m.utc_date, true)}</div>
          </div>
          <div className="flex flex-col items-center text-center gap-2">
            {m.away_team?.crest && <img src={m.away_team.crest} alt="" className="w-14 h-14 sm:w-16 sm:h-16 object-contain" />}
            <div className="font-head font-bold text-slate-50 text-sm sm:text-base">{m.away_team?.shortName || m.away_team?.name}</div>
          </div>
        </div>
      </div>

      {/* Prédiction & confiance */}
      {d.signaux?.probabilites && (
        <div className="card-surface rounded-xl p-5 mb-6" data-testid="prediction-panel">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div>
              <h3 className="font-head font-bold text-slate-100 flex items-center gap-2">
                Probabilités du match <ValueBadge value={d.value} testid="detail-value-badge" />
              </h3>
              <div className="text-[11px] text-slate-500">
                {d.signaux.probabilites.source === "Elo" ? "Modèle Elo" : "Loi de Poisson"}{finished ? " · avant le coup d'envoi" : ""}
              </div>
            </div>
            {d.fiabilite && (
              <span className="text-xs px-2 py-1 rounded font-stat font-bold" data-testid="confidence-badge"
                style={{ color: d.fiabilite.niveau === "Élevée" ? "#10B981" : d.fiabilite.niveau === "Moyenne" ? "#F59E0B" : "#EF4444",
                         backgroundColor: (d.fiabilite.niveau === "Élevée" ? "#10B981" : d.fiabilite.niveau === "Moyenne" ? "#F59E0B" : "#EF4444") + "1A" }}>
                Confiance : {d.fiabilite.niveau}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center mb-3">
            {[["Victoire " + (m.home_team?.tla || "dom."), d.signaux.probabilites.domicile_pct, "#10B981"],
              ["Nul", d.signaux.probabilites.nul_pct, "#64748B"],
              ["Victoire " + (m.away_team?.tla || "ext."), d.signaux.probabilites.exterieur_pct, "#06B6D4"]].map(([l, v, c]) => (
              <div key={l} className="bg-slate-900/50 rounded-lg py-2">
                <div className="font-stat font-black text-2xl" style={{ color: c }}>{v}%</div>
                <div className="text-[10px] text-slate-500 uppercase truncate px-1">{l}</div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 flex-wrap text-xs text-slate-400">
            <span>Scores probables :</span>
            {d.signaux.probabilites.scores_probables.map((s, i) => (
              <span key={i} className="font-stat bg-slate-800 rounded px-2 py-0.5 text-slate-200">{s.score} <span className="text-slate-500">{s.pct}%</span></span>
            ))}
          </div>
          {d.prediction && (
            <div className="mt-3 pt-3 border-t border-slate-800 text-xs text-slate-400" data-testid="elo-note">
              Elo : <b className="text-slate-200">{m.home_team?.shortName || "Dom."} {d.prediction.elo_domicile}</b> ·{" "}
              <b className="text-slate-200">{m.away_team?.shortName || "Ext."} {d.prediction.elo_exterieur}</b> — écart de{" "}
              <b className="text-slate-200">{d.prediction.ecart} pts</b> avantage du terrain compris, en faveur de{" "}
              <b className="text-emerald-400">{d.prediction.favori}</b>.
            </div>
          )}
          {d.cotes && (
            <div className="mt-2 rounded-lg bg-slate-900/50 px-3 py-2" data-testid="detail-odds">
              <OddsLine cotes={d.cotes} value={d.value} />
              <div className="text-[10px] text-slate-500 mt-1">
                {d.cotes.bookmaker ? `Bookmaker : ${d.cotes.bookmaker}. ` : ""}
                {d.value
                  ? `Écart modèle / cote : ${d.value.proba_pct}% estimés contre ${Math.round(100 / d.value.cote)}% implicites (avantage théorique ${d.value.avantage_pct}%). Signal indicatif, non rentable sur l'historique.`
                  : "Aucun écart notable entre le modèle et la cote."}
              </div>
            </div>
          )}
          {(d.repos?.domicile != null || d.repos?.exterieur != null) && (
            <div className="mt-2 text-xs text-slate-500" data-testid="rest-days">
              Repos : {m.home_team?.tla || "Dom."} {d.repos.domicile ?? "?"} j · {m.away_team?.tla || "Ext."} {d.repos.exterieur ?? "?"} j
            </div>
          )}
        </div>
      )}

      {/* Score panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <TeamPanel team={home} side="home" code={m.competition?.code} />
        <TeamPanel team={away} side="away" code={m.competition?.code} />
      </div>

      {/* Radar + avantages */}
      {home && away && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div className="card-surface rounded-xl p-5">
            <h3 className="font-head font-bold text-slate-100 mb-2">Comparaison visuelle</h3>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData} outerRadius="72%" cx="50%" cy="50%">
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis dataKey="stat" tick={{ fill: "#94A3B8", fontSize: 12 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tickCount={5} tick={{ fill: "#475569", fontSize: 9 }} axisLine={false} />
                <Radar name={home.nom_court} dataKey="dom" stroke="#10B981" fill="#10B981" fillOpacity={0.4} isAnimationActive={false} />
                <Radar name={away.nom_court} dataKey="ext" stroke="#06B6D4" fill="#06B6D4" fillOpacity={0.3} isAnimationActive={false} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          <div className="card-surface rounded-xl p-5">
            <h3 className="font-head font-bold text-slate-100 mb-3">Avantages</h3>
            <div className="space-y-2">
              {d.avantages && Object.entries(d.avantages).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0" data-testid={`avantage-${k}`}>
                  <span className="text-sm text-slate-400">{advLabel[k]}</span>
                  {v.gagnant
                    ? <span className="text-sm font-bold text-emerald-400">
                        {v.gagnant}{v.ecart ? <span className="text-slate-500 font-normal ml-1 font-stat">+{v.ecart}</span> : ""}
                      </span>
                    : <DataUnavailable />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <VenueSplit home={home} away={away} />

      {/* Market signals */}
      <div className="mt-6">
        <h2 className="font-head text-xl sm:text-2xl font-bold text-slate-50 mb-3 flex items-center gap-2">
          <Swords className="w-5 h-5 text-emerald-400" /> Analyse des marchés
        </h2>
        <MarketSignals data={d.signaux} />
      </div>

      {/* Players to watch */}
      <div className="mt-6">
        <h2 className="font-head text-xl sm:text-2xl font-bold text-slate-50 mb-3 flex items-center gap-2">
          <Users className="w-5 h-5 text-emerald-400" /> Joueurs à surveiller
        </h2>
        {d.joueurs?.disponible ? (
          <div data-testid="players-section">
            <p className="text-xs text-slate-500 mb-3">{d.joueurs.source}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-sm font-semibold text-emerald-400 mb-2">{m.home_team?.shortName || m.home_team?.name}</div>
                <div className="space-y-3">
                  {(d.joueurs.domicile || []).length
                    ? d.joueurs.domicile.map((p) => <PlayerWatchCard key={p.player_id} player={p} side="home" form={formMap[p.player_id]} />)
                    : <DataUnavailable label="Aucun joueur avec assez de minutes" />}
                </div>
              </div>
              <div>
                <div className="text-sm font-semibold text-cyan-400 mb-2">{m.away_team?.shortName || m.away_team?.name}</div>
                <div className="space-y-3">
                  {(d.joueurs.exterieur || []).length
                    ? d.joueurs.exterieur.map((p) => <PlayerWatchCard key={p.player_id} player={p} side="away" form={formMap[p.player_id]} />)
                    : <DataUnavailable label="Aucun joueur avec assez de minutes" />}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="card-surface rounded-xl p-6 text-center" data-testid="players-section">
            <DataUnavailable label="Données joueurs indisponibles" />
            <p className="text-sm text-slate-400 mt-3 max-w-md mx-auto">{d.joueurs?.message}</p>
          </div>
        )}
      </div>

      {/* Head to head */}
      {d.confrontations?.length > 0 && (
        <div className="mt-6">
          <h2 className="font-head text-xl sm:text-2xl font-bold text-slate-50 mb-3 flex items-center gap-2">
            <History className="w-5 h-5 text-emerald-400" /> Confrontations directes
          </h2>
          <div className="card-surface rounded-xl p-4 space-y-2" data-testid="head-to-head">
            {d.confrontations.map((c, i) => (
              <div key={i} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-800 last:border-0">
                <span className="text-slate-400 w-24 shrink-0">{frDate(c.date, true)}</span>
                <span className="text-slate-200 flex-1 text-right truncate">{c.domicile}</span>
                <span className="font-stat font-bold text-slate-100 mx-3">{c.score}</span>
                <span className="text-slate-200 flex-1 truncate">{c.exterieur}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
