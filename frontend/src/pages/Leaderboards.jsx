import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { ScoreBadge } from "../components/ScoreBadge";
import { PlayerRow } from "../components/PlayerCard";
import { FormChips } from "../components/FormChips";
import { DataUnavailable } from "../components/DataUnavailable";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Trophy, Users } from "lucide-react";

export default function Leaderboards() {
  const [comps, setComps] = useState([]);
  const [code, setCode] = useState(null);
  const [teams, setTeams] = useState(null);
  const [loading, setLoading] = useState(true);
  const [players, setPlayers] = useState(null);
  const [ploading, setPloading] = useState(true);

  useEffect(() => { api.get("/competitions").then((r) => setComps(r.data)).catch(() => {}); }, []);

  useEffect(() => {
    setLoading(true);
    const params = code ? { code } : {};
    api.get("/leaderboard/teams", { params })
      .then((r) => setTeams(r.data)).catch(() => setTeams([])).finally(() => setLoading(false));
  }, [code]);

  useEffect(() => {
    setPloading(true);
    api.get("/leaderboard/players")
      .then((r) => setPlayers(r.data)).catch(() => setPlayers(null)).finally(() => setPloading(false));
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1">Classements</h1>
      <p className="text-slate-400 text-sm mb-6">Équipes classées par score global de forme sur 100.</p>

      <Tabs defaultValue="equipes">
        <TabsList className="bg-slate-900/60 border border-slate-800">
          <TabsTrigger value="equipes" data-testid="tab-teams" className="data-[state=active]:bg-emerald-500 data-[state=active]:text-white">
            <Trophy className="w-4 h-4 mr-1.5" /> Meilleures équipes
          </TabsTrigger>
          <TabsTrigger value="joueurs" data-testid="tab-players" className="data-[state=active]:bg-emerald-500 data-[state=active]:text-white">
            <Users className="w-4 h-4 mr-1.5" /> Meilleurs joueurs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="equipes" className="mt-4">
          <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-4">
            <button onClick={() => setCode(null)} data-testid="lb-league-all"
              className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap ${!code ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-300"}`}>Tous</button>
            {comps.map((c) => (
              <button key={c.code} onClick={() => setCode(c.code)} data-testid={`lb-league-${c.code.toLowerCase()}`}
                className={`px-3 py-1.5 rounded-full text-sm whitespace-nowrap ${code === c.code ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-300"}`}>{c.nom}</button>
            ))}
          </div>

          {loading ? (
            <div className="space-y-2">{[...Array(8)].map((_, i) => <Skeleton key={i} className="h-16 rounded-xl bg-slate-800/50" />)}</div>
          ) : (
            <div className="space-y-2" data-testid="teams-leaderboard">
              {(teams || []).map((t, i) => (
                <Link key={`${t.competition_code}-${t.team_id}`} to={`/equipe/${t.competition_code}/${t.team_id}`}
                  data-testid={`lb-team-${t.team_id}`} className="card-surface rounded-xl p-3 flex items-center gap-3">
                  <div className="w-7 text-center font-stat font-black text-slate-500">{i + 1}</div>
                  {t.logo ? <img src={t.logo} alt="" className="w-9 h-9 object-contain" /> : <div className="w-9 h-9 rounded bg-slate-800" />}
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-slate-100 text-sm truncate">{t.nom_court || t.nom}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] text-slate-500">{t.competition_nom}</span>
                      <FormChips form={t.forme_recente} />
                    </div>
                  </div>
                  <ScoreBadge score={t.global} size="sm" />
                </Link>
              ))}
              {(teams || []).length === 0 && <div className="text-center text-slate-500 py-10">Aucune donnée disponible.</div>}
            </div>
          )}
        </TabsContent>

        <TabsContent value="joueurs" className="mt-4">
          {ploading ? (
            <div className="space-y-2">{[...Array(8)].map((_, i) => <Skeleton key={i} className="h-16 rounded-xl bg-slate-800/50" />)}</div>
          ) : players?.disponible ? (
            <>
              <p className="text-xs text-slate-500 mb-3">
                Classés par score joueur /100 · min. {players.min_minutes} minutes jouées · source Understat (saison en cours).
              </p>
              <div className="space-y-2" data-testid="players-leaderboard">
                {players.joueurs.map((p, i) => (
                  <PlayerRow key={p.player_id} player={p} rank={i + 1} testid={`lb-player-${p.player_id}`} />
                ))}
              </div>
            </>
          ) : (
            <div className="card-surface rounded-xl p-8 text-center" data-testid="players-leaderboard-unavailable">
              <DataUnavailable label="Classement joueurs indisponible" />
              <p className="text-sm text-slate-400 mt-3 max-w-md mx-auto">{players?.message || "Données non disponibles."}</p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
