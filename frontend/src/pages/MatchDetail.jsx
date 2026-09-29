import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { MarketSignals } from "../components/MarketSignals";
import { PlayerWatchCard } from "../components/PlayerCard";
import { DataUnavailable } from "../components/DataUnavailable";
import { FormChips } from "../components/FormChips";
import { OddsLine, ValueBadge } from "../components/Probabilities";
import { BestMethodBadge, ForecastNumbers, ModelTag, MODEL_NAME } from "../components/Forecast";
import { frDate, kickoff, scoreColor } from "../lib/format";
import { Skeleton } from "../components/ui/skeleton";
import { ArrowLeft, Trophy, Users, History, Swords, Scale } from "lucide-react";

const fmtSigned = (v, digits = 2) => `${v > 0 ? "+" : ""}${v.toFixed(digits).replace(".", ",")}`;

// Les deux équipes côte à côte : force Elo et forme xG (ce qu'utilise le pronostic), puis
// la note de forme /100 et ses composantes (indicateurs descriptifs).
function TeamsComparison({ home, away, code, noteHist }) {
  if (!home || !away) {
    return <div className="card-surface rounded-xl p-5"><DataUnavailable label="Analyse des équipes indisponible" /></div>;
  }
  const eloRank = (t) => (t.elo?.rang ? `${t.elo.rang}e sur ${t.elo.sur}` : "");
  const note = (t, k, title) => t[k] ? (
    <ScoreBreakdown data={t[k]} title={title} team={t.nom_court} testid={`score-breakdown-${k}-${t === home ? "home" : "away"}`}>
      <button className="font-stat font-bold underline decoration-dotted decoration-slate-600 underline-offset-4"
        style={{ color: scoreColor(t[k].score) }}>{t[k].score}</button>
    </ScoreBreakdown>
  ) : <span className="text-slate-600">—</span>;
  const venueScore = (v) => (v == null ? <span className="text-slate-600">—</span>
    : <span className="font-stat" style={{ color: scoreColor(v) }}>{v}</span>);
  const better = (a, b, higher = true) => (a == null || b == null || a === b ? null : (a > b) === higher ? "h" : "a");

  const primary = [
    ["Force Elo", home.elo?.elo, away.elo?.elo,
      (t) => t.elo ? <><b className="font-stat text-slate-100">{t.elo.elo}</b><span className="block text-slate-500 text-[10px]">{eloRank(t)}</span></> : "—",
      "team-elo"],
    ["Forme xG par match", home.elo?.forme_xg, away.elo?.forme_xg,
      (t) => t.elo?.forme_xg != null ? <span className="font-stat text-slate-100">{fmtSigned(t.elo.forme_xg)}</span> : <span className="text-slate-600">—</span>],
    ["5 derniers matchs", null, null, (t) => <FormChips form={t.stats?.forme_recente} />],
    ["Classement", home.classement?.position, away.classement?.position,
      (t) => t.classement ? <span className="font-stat text-slate-300">{t.classement.position}e · {t.classement.points} pts</span> : "—", null, false],
  ];
  const secondary = [
    ["Note de forme /100", "global", "Note de forme"],
    ["Attaque /100", "offensif", "Attaque"],
    ["Défense /100", "defensif", "Défense"],
    ["Résultats /100", "forme", "Résultats"],
  ];

  const Cell = ({ side, children }) => (
    <td className={`py-2 px-1 sm:px-2 ${side === "h" ? "text-left" : "text-right"}`}>{children}</td>
  );

  return (
    <div className="card-surface rounded-xl p-5" data-testid="teams-compare">
      <h2 className="font-head text-lg font-bold text-slate-50 mb-3 flex items-center gap-2">
        <Scale className="w-5 h-5 text-emerald-400" /> Les deux équipes
      </h2>
      <table className="w-full text-sm table-fixed">
        <thead>
          <tr className="border-b border-slate-800">
            {[["h", home], [null, null], ["a", away]].map(([side, t], i) => side ? (
              <th key={i} className={`py-2 px-1 sm:px-2 w-[37%] ${side === "h" ? "text-left" : "text-right"}`}>
                <Link to={`/equipe/${code}/${t.team_id}`} data-testid={`team-link-${side === "h" ? "home" : "away"}`}
                  className={`flex items-center gap-2 font-head font-bold text-slate-50 hover:text-emerald-400 min-w-0 ${side === "a" ? "flex-row-reverse" : ""}`}>
                  {t.logo && <img src={t.logo} alt="" className="w-6 h-6 object-contain shrink-0" />}
                  <span className="truncate">{t.nom_court || t.nom}</span>
                </Link>
              </th>
            ) : <th key={i} />)}
          </tr>
        </thead>
        <tbody>
          {primary.map(([label, hv, av, render, testid, higher = true]) => {
            const b = better(hv, av, higher);
            return (
              <tr key={label} className="border-b border-slate-800/60">
                <Cell side="h"><span data-testid={testid ? `${testid}-home` : undefined} className={`inline-flex flex-col items-start ${b === "a" ? "opacity-60" : ""}`}>{render(home)}</span></Cell>
                <td className="py-2 px-1 text-center text-[10px] sm:text-[11px] leading-tight text-slate-400">{label}</td>
                <Cell side="a"><span data-testid={testid ? `${testid}-away` : undefined} className={`inline-flex flex-col items-end ${b === "h" ? "opacity-60" : ""}`}>{render(away)}</span></Cell>
              </tr>
            );
          })}
          <tr><td colSpan={3} className="pt-4 pb-1 text-[10px] uppercase tracking-wide text-slate-500">
            Note de forme /100 · 10 derniers matchs du championnat (descriptif)
          </td></tr>
          {secondary.map(([label, k, title]) => (
            <tr key={k} className="border-b border-slate-800/60" data-testid={`compare-row-${k}`}>
              <Cell side="h">{note(home, k, title)}</Cell>
              <td className="py-2 px-1 text-center text-[10px] sm:text-[11px] leading-tight text-slate-400">{label}</td>
              <Cell side="a">{note(away, k, title)}</Cell>
            </tr>
          ))}
          <tr className="border-b border-slate-800/60">
            <Cell side="h">{venueScore(home.domicile?.score)}</Cell>
            <td className="py-2 px-1 text-center text-[10px] sm:text-[11px] leading-tight text-slate-400">À domicile · à l'extérieur</td>
            <Cell side="a">{venueScore(away.exterieur?.score)}</Cell>
          </tr>
          <tr>
            <Cell side="h"><span className="font-stat text-slate-300">{home.stats ? `${home.stats.buts_marques} – ${home.stats.buts_encaisses}` : "—"}</span></Cell>
            <td className="py-2 px-1 text-center text-[10px] sm:text-[11px] leading-tight text-slate-400">Buts pour – contre</td>
            <Cell side="a"><span className="font-stat text-slate-300">{away.stats ? `${away.stats.buts_marques} – ${away.stats.buts_encaisses}` : "—"}</span></Cell>
          </tr>
        </tbody>
      </table>
      {noteHist && (
        <div className="mt-4 rounded-lg bg-slate-900/50 p-3 text-xs text-slate-400" data-testid="note-history">
          <div className="mb-1.5">
            Notes /100 : <b className="text-slate-200">{home.nom_court} {home.global?.score}</b> contre{" "}
            <b className="text-slate-200">{away.nom_court} {away.global?.score}</b> (écart {noteHist.ecart}). Par le passé, quand
            l'équipe la mieux notée (ici {home.global?.score > away.global?.score ? home.nom_court : away.nom_court}) jouait{" "}
            {noteHist.terrain === "domicile" ? "à domicile" : "à l'extérieur"} avec un écart de {noteHist.tranche} ({noteHist.matchs} matchs) :
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[["victoire", noteHist.favori_gagne_pct], ["nul", noteHist.nul_pct], ["défaite", noteHist.outsider_gagne_pct]].map(([l, v]) => (
              <div key={l} className="bg-slate-800/60 rounded-md py-1">
                <div className="font-stat font-bold text-sm text-slate-200">{v}%</div>
                <div className="text-[10px] text-slate-500">{l}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="mt-3 text-[11px] text-slate-500">
        Le pronostic repose sur la force Elo et la forme xG. La note de forme /100 résume les derniers résultats ;
        elle prévoit nettement moins bien les matchs (<Link to="/methodologie#classement" className="underline hover:text-slate-300">classement des méthodes</Link>).
      </p>
    </div>
  );
}

export default function MatchDetail() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [formMap, setFormMap] = useState({});
  const [noteHist, setNoteHist] = useState(null);

  useEffect(() => {
    setLoading(true);
    setFormMap({});
    setNoteHist(null);
    api.get(`/match/${id}`).then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
  }, [id]);

  // Matchs passés au même écart de notes /100 (championnats, match à venir uniquement)
  const noteDom = d?.domicile?.global?.score, noteExt = d?.exterieur?.global?.score;
  const upcomingLeague = d && d.match.status !== "FINISHED" && !d.match.competition?.coupe;
  useEffect(() => {
    if (!upcomingLeague || noteDom == null || noteExt == null || noteDom === noteExt) return;
    api.get("/stats/ecart-notes", { params: { domicile: noteDom, exterieur: noteExt } })
      .then((r) => setNoteHist(r.data?.historique || null)).catch(() => {});
  }, [upcomingLeague, noteDom, noteExt]);

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

      {/* Pronostic FootPulse : la meilleure méthode testée, mise en avant */}
      {d.signaux?.probabilites && (() => {
        const p = d.prediction;
        const homeName = m.home_team?.shortName || "Dom.", awayName = m.away_team?.shortName || "Ext.";
        const probs = p || { domicile_pct: d.signaux.probabilites.domicile_pct, nul_pct: d.signaux.probabilites.nul_pct,
                             exterieur_pct: d.signaux.probabilites.exterieur_pct };
        const conf = d.fiabilite?.niveau;
        const confColor = conf === "Élevée" ? "#10B981" : conf === "Moyenne" ? "#F59E0B" : "#EF4444";
        return (
          <div className="card-surface rounded-xl p-5 mb-6 border border-emerald-500/20" data-testid="prediction-panel">
            <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
              <div>
                <h2 className="font-head text-xl font-bold text-slate-50 flex items-center gap-2 flex-wrap">
                  {MODEL_NAME} <ValueBadge value={d.value} testid="detail-value-badge" />
                </h2>
                <div className="mt-1 flex items-center gap-2 flex-wrap">
                  {d.signaux.probabilites.source === "Elo"
                    ? <ModelTag modele={p?.modele} testid="detail-model" />
                    : <span className="text-[11px] text-slate-500">Loi de Poisson</span>}
                  <BestMethodBadge />
                  {finished && <span className="text-[11px] text-slate-500">calculé avant le coup d'envoi</span>}
                </div>
              </div>
              {conf && (
                <span className="text-xs px-2 py-1 rounded font-stat font-bold" data-testid="confidence-badge"
                  style={{ color: confColor, backgroundColor: confColor + "1A" }}>
                  Confiance : {conf}
                </span>
              )}
            </div>

            <ForecastNumbers pred={probs} homeName={homeName} awayName={awayName} size="lg" testid="detail-probas" />

            {p && (
              <div className="mt-4 text-sm text-slate-300" data-testid="detail-favourite">
                Favori : <b className="text-emerald-300">{p.favori}</b> ({Math.round(p.favori_pct)} %)
                {p.favori_pct < 45 ? " · match très ouvert" : ""}
              </div>
            )}

            {p && (() => {
              const eloHome = p.elo_domicile + (p.avantage_terrain || 0) >= p.elo_exterieur;
              return (
                <div className="mt-3 rounded-lg bg-slate-900/50 p-3 text-xs text-slate-400 space-y-1.5" data-testid="elo-note">
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">Pourquoi ce pronostic</div>
                  <div>
                    <b className="text-slate-300">Force Elo</b> : {homeName} {p.elo_domicile}
                    {p.avantage_terrain ? <> + {p.avantage_terrain} à domicile = <b className="text-slate-200">{p.elo_domicile + p.avantage_terrain}</b></> : null}
                    {" "}contre {awayName} <b className="text-slate-200">{p.elo_exterieur}</b> (avantage {eloHome ? homeName : awayName}, {p.ecart} pts).
                  </div>
                  {p.xg_domicile !== null && p.xg_domicile !== undefined && (
                    <div data-testid="xg-note">
                      <b className="text-slate-300">Forme xG</b> (occasions créées − concédées par match, derniers matchs) :{" "}
                      {homeName} <b className="text-slate-200">{fmtSigned(p.xg_domicile)}</b> · {awayName} <b className="text-slate-200">{fmtSigned(p.xg_exterieur)}</b>.
                    </div>
                  )}
                </div>
              );
            })()}

            <div className="mt-3 flex items-center gap-2 flex-wrap text-xs text-slate-400">
              <span>Scores probables :</span>
              {d.signaux.probabilites.scores_probables.map((sp, i) => (
                <span key={i} className="font-stat bg-slate-800 rounded px-2 py-0.5 text-slate-200">{sp.score} <span className="text-slate-500">{sp.pct}%</span></span>
              ))}
            </div>

            {d.cotes && (
              <div className="mt-3 rounded-lg bg-slate-900/50 px-3 py-2" data-testid="detail-odds">
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
        );
      })()}

      <TeamsComparison home={home} away={away} code={m.competition?.code} noteHist={noteHist} />

      {/* Market signals */}
      <div className="mt-6">
        <h2 className="font-head text-xl sm:text-2xl font-bold text-slate-50 mb-3 flex items-center gap-2">
          <Swords className="w-5 h-5 text-emerald-400" /> Marchés : buts et BTTS
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
