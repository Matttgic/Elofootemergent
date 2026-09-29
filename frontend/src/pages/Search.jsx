import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { DataUnavailable } from "../components/DataUnavailable";
import { TeamLogo } from "../components/TeamLogo";
import { Skeleton } from "../components/ui/skeleton";
import { SearchX } from "lucide-react";

export default function Search() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (q.length < 2) return;
    setLoading(true);
    api.get("/search", { params: { q } }).then((r) => setRes(r.data)).catch(() => setRes(null)).finally(() => setLoading(false));
  }, [q]);

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-2xl sm:text-3xl font-extrabold text-slate-50 mb-1">Résultats de recherche</h1>
      <p className="text-slate-400 text-sm mb-6">« {q} »</p>

      {loading ? (
        <div className="space-y-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-14 rounded-xl bg-slate-800/50" />)}</div>
      ) : (
        <>
          <h2 className="font-head font-bold text-slate-200 mb-2">Équipes</h2>
          {res?.equipes?.length ? (
            <div className="space-y-2 mb-6" data-testid="search-teams">
              {res.equipes.map((t) => (
                <Link key={t.team_id} to={`/equipe/${t.competition_code}/${t.team_id}`}
                  data-testid={`search-team-${t.team_id}`} className="card-surface rounded-xl p-3 flex items-center gap-3">
                  {t.logo ? <img src={t.logo} alt="" className="w-9 h-9 object-contain" /> : <div className="w-9 h-9 rounded bg-slate-800" />}
                  <div><div className="font-semibold text-slate-100 text-sm">{t.nom}</div>
                    <div className="text-xs text-slate-500">{t.competition_nom}</div></div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="card-surface rounded-xl p-6 text-center text-slate-400 mb-6" data-testid="search-no-teams">
              <SearchX className="w-8 h-8 mx-auto mb-2 text-slate-600" />Aucune équipe trouvée.
            </div>
          )}

          <h2 className="font-head font-bold text-slate-200 mb-2">Joueurs</h2>
          {res?.joueurs?.disponible ? (
            <div className="space-y-2" data-testid="search-players">
              {res.joueurs.resultats.map((p) => (
                <div key={p.player_id} data-testid={`search-player-${p.player_id}`}
                  className="card-surface rounded-xl p-3 flex items-center gap-3">
                  {p.team_logo ? <TeamLogo src={p.team_logo} className="w-9 h-9" /> : <div className="w-9 h-9 rounded bg-slate-800 shrink-0" />}
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-slate-100 text-sm truncate">{p.nom}</div>
                    <div className="text-xs text-slate-500">{p.poste} · {p.team_title} · {p.competition_nom}</div>
                  </div>
                  <span className="font-stat font-bold text-emerald-400">{p.score}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="card-surface rounded-xl p-6 text-center">
              <DataUnavailable label="Aucun joueur trouvé" />
              <p className="text-sm text-slate-400 mt-3">{res?.joueurs?.message}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
