import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { ScoreBadge } from "../components/ScoreBadge";
import { PlayerRow } from "../components/PlayerCard";
import { FormChips } from "../components/FormChips";
import { DataUnavailable } from "../components/DataUnavailable";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Trophy, Users, Goal, Handshake, Star } from "lucide-react";
import { useFavorites } from "../lib/useFavorites";

const POSTES = ["Tous", "Attaquant", "Milieu", "Défenseur", "Gardien"];

const PLAYER_TABS = {
  joueurs: { tri: "global", metric: "global", note: "score joueur /100" },
  buteurs: { tri: "buteurs", metric: "buts", note: "nombre de buts (saison en cours)" },
  passeurs: { tri: "passeurs", metric: "passes", note: "passes décisives (saison en cours)" },
};

export default function Leaderboards() {
  const [comps, setComps] = useState([]);
  const [code, setCode] = useState(null);
  const [teams, setTeams] = useState(null);
  const [teamSort, setTeamSort] = useState("elo");
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("equipes");
  const [playersByTri, setPlayersByTri] = useState({});
  const [poste, setPoste] = useState("Tous");
  const { isFav, toggle } = useFavorites();

  useEffect(() => { api.get("/competitions").then((r) => setComps(r.data)).catch(() => {}); }, []);

  useEffect(() => {
    setLoading(true);
    const params = { tri: teamSort, ...(code ? { code } : {}) };
    api.get("/leaderboard/teams", { params })
      .then((r) => setTeams(r.data)).catch(() => setTeams([])).finally(() => setLoading(false));
  }, [code, teamSort]);

  // Une seule requête par (tri, poste), y compris en cas d'échec : l'erreur est
  // mémorisée (null) au lieu de relancer la requête en boucle.
  const requested = useRef(new Set());
  const loadPlayers = useCallback((tri) => {
    const key = `${tri}|${poste}`;
    if (requested.current.has(key)) return;
    requested.current.add(key);
    api.get("/leaderboard/players", { params: { tri, poste } })
      .then((r) => setPlayersByTri((prev) => ({ ...prev, [key]: r.data })))
      .catch(() => setPlayersByTri((prev) => ({ ...prev, [key]: null })));
  }, [poste]);

  useEffect(() => {
    const cfg = PLAYER_TABS[tab];
    if (cfg) loadPlayers(cfg.tri);
  }, [tab, loadPlayers]);

  const renderPlayers = (key) => {
    const cfg = PLAYER_TABS[key];
    const dataKey = `${cfg.tri}|${poste}`;
    const data = playersByTri[dataKey];
    const posteFilter = (
      <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-3" data-testid="poste-filter">
        {POSTES.map((pz) => (
          <button key={pz} onClick={() => setPoste(pz)} data-testid={`poste-${pz.toLowerCase()}`}
            className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap ${
              poste === pz ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-300"}`}>{pz}</button>
        ))}
      </div>
    );
    if (!(dataKey in playersByTri)) {
      return <>{posteFilter}<div className="space-y-2">{[...Array(8)].map((_, i) => <Skeleton key={i} className="h-16 rounded-xl bg-slate-800/50" />)}</div></>;
    }
    if (!data?.disponible) {
      return (
        <>{posteFilter}
          <div className="card-surface rounded-xl p-8 text-center" data-testid="players-leaderboard-unavailable">
            <DataUnavailable label="Classement indisponible" />
            <p className="text-sm text-slate-400 mt-3 max-w-md mx-auto">{data?.message || "Aucun joueur pour ce filtre."}</p>
          </div>
        </>
      );
    }
    return (
      <>
        {posteFilter}
        <p className="text-xs text-slate-500 mb-3">
          Classés par {cfg.note} · min. {data.min_minutes} min jouées · 5 grands championnats (Understat) + Portugal et Pays-Bas (FotMob).
        </p>
        <div className="space-y-2" data-testid={`players-leaderboard-${key}`}>
          {data.joueurs.map((p, i) => (
            <PlayerRow key={p.player_id} player={p} rank={i + 1} metric={cfg.metric} testid={`lb-player-${p.player_id}`} />
          ))}
        </div>
      </>
    );
  };

  const triggerCls = "data-[state=active]:bg-emerald-500 data-[state=active]:text-white text-xs sm:text-sm";

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1">Classements</h1>
      <p className="text-slate-400 text-sm mb-6">Équipes et joueurs des grands championnats européens.</p>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-slate-900/60 border border-slate-800 flex-wrap h-auto">
          <TabsTrigger value="equipes" data-testid="tab-teams" className={triggerCls}>
            <Trophy className="w-4 h-4 mr-1.5" /> Équipes
          </TabsTrigger>
          <TabsTrigger value="joueurs" data-testid="tab-players" className={triggerCls}>
            <Users className="w-4 h-4 mr-1.5" /> Joueurs
          </TabsTrigger>
          <TabsTrigger value="buteurs" data-testid="tab-buteurs" className={triggerCls}>
            <Goal className="w-4 h-4 mr-1.5" /> Buteurs
          </TabsTrigger>
          <TabsTrigger value="passeurs" data-testid="tab-passeurs" className={triggerCls}>
            <Handshake className="w-4 h-4 mr-1.5" /> Passeurs
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

          <div className="flex items-center gap-2 mb-4 text-xs" data-testid="team-sort">
            <span className="text-slate-500">Trier par</span>
            {[["elo", "Elo"], ["note", "Note /100"]].map(([k, l]) => (
              <button key={k} onClick={() => setTeamSort(k)} data-testid={`team-sort-${k}`}
                className={`px-3 py-1 rounded-full font-medium ${teamSort === k ? "bg-cyan-500 text-white" : "bg-slate-800/60 text-slate-400"}`}>{l}</button>
            ))}
            <span className="text-slate-600 hidden sm:inline">
              {teamSort === "elo" ? "· force sur la durée, comparable entre championnats" : "· forme sur les 10 derniers matchs"}
            </span>
          </div>

          {loading ? (
            <div className="space-y-2">{[...Array(8)].map((_, i) => <Skeleton key={i} className="h-16 rounded-xl bg-slate-800/50" />)}</div>
          ) : (
            <div className="space-y-2" data-testid="teams-leaderboard">
              {(teams || []).map((t, i) => (
                <div key={`${t.competition_code}-${t.team_id}`} className="relative">
                  <Link to={`/equipe/${t.competition_code}/${t.team_id}`}
                    data-testid={`lb-team-${t.team_id}`} className="card-surface rounded-xl p-3 pr-11 flex items-center gap-3">
                    <div className="w-7 text-center font-stat font-black text-slate-500">{i + 1}</div>
                    {t.logo ? <img src={t.logo} alt="" className="w-9 h-9 object-contain" /> : <div className="w-9 h-9 rounded bg-slate-800" />}
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-slate-100 text-sm truncate">{t.nom_court || t.nom}</div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px] text-slate-500">{t.competition_nom}</span>
                        <FormChips form={t.forme_recente} />
                      </div>
                    </div>
                    {t.elo && (
                      <div className="text-right shrink-0" data-testid={`lb-team-elo-${t.team_id}`}>
                        <div className="font-stat font-bold text-sm text-slate-100 tabular-nums">{t.elo}</div>
                        <div className="text-[9px] uppercase text-slate-500">Elo</div>
                      </div>
                    )}
                    <ScoreBadge score={t.global} size="sm" />
                  </Link>
                  <button data-testid={`fav-toggle-${t.team_id}`}
                    onClick={(e) => { e.preventDefault(); toggle({ team_id: t.team_id, nom: t.nom_court || t.nom, logo: t.logo, competition_code: t.competition_code }); }}
                    className="absolute top-1/2 -translate-y-1/2 right-2 p-1.5 rounded-md hover:bg-slate-800 z-10">
                    <Star className={`w-4 h-4 ${isFav(t.team_id) ? "text-amber-400 fill-amber-400" : "text-slate-600"}`} />
                  </button>
                </div>
              ))}
              {(teams || []).length === 0 && <div className="text-center text-slate-500 py-10">Aucune donnée disponible.</div>}
            </div>
          )}
        </TabsContent>

        <TabsContent value="joueurs" className="mt-4">{renderPlayers("joueurs")}</TabsContent>
        <TabsContent value="buteurs" className="mt-4">{renderPlayers("buteurs")}</TabsContent>
        <TabsContent value="passeurs" className="mt-4">{renderPlayers("passeurs")}</TabsContent>
      </Tabs>
    </div>
  );
}
