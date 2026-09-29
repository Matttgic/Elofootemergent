import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { MatchCard } from "../components/MatchCard";
import { frDate, frDateShort, todayISO, timeAgo } from "../lib/format";
import { Skeleton } from "../components/ui/skeleton";
import { ChevronLeft, ChevronRight, CalendarDays, AlertCircle, RefreshCw, ArrowDownWideNarrow, Zap } from "lucide-react";
import { Button } from "../components/ui/button";
import { motion } from "framer-motion";
import { useFavorites } from "../lib/useFavorites";
import { Link } from "react-router-dom";
import { Star } from "lucide-react";

function SyncBanner({ status }) {
  if (!status || status.token_present) return null;
  return (
    <div className="card-surface rounded-xl p-5 border-amber-500/30 bg-amber-500/5 mb-6" data-testid="sync-banner-token">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-sm text-slate-300">
          <b className="text-amber-300">Clé API football-data.org requise.</b> Les données réelles
          seront chargées dès que la clé sera configurée. Aucune donnée fictive n'est affichée.
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [status, setStatus] = useState(null);
  const [comps, setComps] = useState([]);
  const [code, setCode] = useState(null);
  const [date, setDate] = useState(todayISO());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statut, setStatut] = useState("tous");
  const [dates, setDates] = useState([]);
  const [tri, setTri] = useState("heure");
  const [valueOnly, setValueOnly] = useState(false);
  const { favs } = useFavorites();

  const loadStatus = useCallback(() => {
    api.get("/status").then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    loadStatus();
    api.get("/competitions").then((r) => setComps(r.data)).catch(() => {});
  }, [loadStatus]);

  const loadMatches = useCallback(() => {
    setLoading(true);
    const params = { date };
    if (code) params.code = code;
    api.get("/matches", { params })
      .then((r) => setData(r.data))
      .catch(() => setData({ matchs: [] }))
      .finally(() => setLoading(false));
  }, [code, date]);

  useEffect(() => { loadMatches(); }, [loadMatches]);

  // Dates ayant des matchs (pour proposer la journée précédente / suivante)
  useEffect(() => {
    api.get("/dates", { params: code ? { code } : {} }).then((r) => setDates(r.data)).catch(() => setDates([]));
  }, [code]);
  const nextDate = dates.find((d) => d > date);
  const prevDate = [...dates].reverse().find((d) => d < date);

  const shiftDay = (delta) => {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + delta);
    setDate(d.toLocaleDateString("en-CA"));
  };

  const allMatchs = data?.matchs || [];
  let matchs = allMatchs.filter((m) => {
    if (statut === "a_venir") return !["FINISHED", "IN_PLAY", "PAUSED"].includes(m.status);
    if (statut === "termines") return m.status === "FINISHED";
    return true;
  });
  if (valueOnly) matchs = matchs.filter((m) => m.value);
  if (tri === "ecart") {
    matchs = [...matchs].sort((a, b) => (b.prediction?.favori_pct ?? -1) - (a.prediction?.favori_pct ?? -1));
  }
  const valueCount = allMatchs.filter((m) => m.value).length;

  return (
    <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="font-head text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-slate-50">
            Matchs & Analyse
          </h1>
          <p className="text-slate-400 text-sm sm:text-base mt-1">
            Notes Elo, probabilités et analyse statistique des grands championnats européens.
          </p>
        </div>
        {status?.token_present && (
          <div className="flex items-center gap-2 card-surface rounded-lg px-3 py-2" data-testid="sync-status-bar">
            <RefreshCw className="w-4 h-4 text-emerald-400 shrink-0" />
            <div className="text-xs text-slate-400 leading-tight">
              <div>Données à jour · <span className="text-slate-200 font-medium" data-testid="last-sync-label">
                {status.synchronisation_en_cours ? "actualisation…" : timeAgo(status.derniere_synchro?.last_sync)}
              </span></div>
              <div className="text-[10px] text-slate-500">Mise à jour automatique chaque heure</div>
            </div>
          </div>
        )}
      </div>
      </motion.div>

      <SyncBanner status={status} />

      {favs.length > 0 && (
        <div className="mb-4" data-testid="favorites-strip">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-2 font-semibold">
            <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" /> Mes équipes
          </div>
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {favs.map((f) => (
              <Link key={f.team_id} to={`/equipe/${f.competition_code}/${f.team_id}`} data-testid={`fav-team-${f.team_id}`}
                className="card-surface rounded-lg px-3 py-1.5 flex items-center gap-2 shrink-0">
                {f.logo && <img src={f.logo} alt="" className="w-5 h-5 object-contain" />}
                <span className="text-sm text-slate-200 whitespace-nowrap">{f.nom}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Date navigation */}
      <div className="flex items-center gap-2 mb-4">
        <Button size="icon" variant="outline" onClick={() => shiftDay(-1)}
          data-testid="date-prev" className="border-slate-700 shrink-0"><ChevronLeft className="w-4 h-4" /></Button>
        <div className="card-surface rounded-lg px-3 h-10 flex items-center gap-2 flex-1 justify-center relative">
          <CalendarDays className="w-4 h-4 text-emerald-400" />
          <span className="font-head font-bold text-slate-100 capitalize">
            {date === todayISO() ? "Aujourd'hui · " : ""}{frDate(date + "T12:00:00", true)}
          </span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            data-testid="date-picker" className="absolute inset-0 opacity-0 cursor-pointer" />
        </div>
        <Button size="icon" variant="outline" onClick={() => shiftDay(1)}
          data-testid="date-next" className="border-slate-700 shrink-0"><ChevronRight className="w-4 h-4" /></Button>
      </div>

      {/* League filter */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-6 -mx-1 px-1">
        <button onClick={() => setCode(null)} data-testid="league-filter-all"
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            !code ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-300 hover:bg-slate-800"}`}>
          Tous
        </button>
        {comps.map((c) => (
          <button key={c.code} onClick={() => setCode(c.code)}
            data-testid={`league-filter-${c.code.toLowerCase()}`}
            className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
              code === c.code ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-300 hover:bg-slate-800"}`}>
            {c.nom}
          </button>
        ))}
      </div>

      {/* Status filter + sort + value */}
      <div className="flex items-center gap-2 mb-6 flex-wrap">
        {[["tous", "Tous"], ["a_venir", "À venir"], ["termines", "Terminés"]].map(([v, l]) => (
          <button key={v} onClick={() => setStatut(v)} data-testid={`status-filter-${v}`}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              statut === v ? "bg-cyan-500 text-white" : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"}`}>
            {l}
          </button>
        ))}
        <span className="w-px h-5 bg-slate-700 mx-1" />
        <button onClick={() => setTri(tri === "ecart" ? "heure" : "ecart")} data-testid="sort-ecart-toggle"
          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            tri === "ecart" ? "bg-emerald-500 text-white" : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"}`}>
          <ArrowDownWideNarrow className="w-3.5 h-3.5" /> Trier par favori
        </button>
        <button onClick={() => setValueOnly((v) => !v)} data-testid="value-filter-toggle"
          className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            valueOnly ? "bg-amber-500 text-slate-900" : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"}`}>
          <Zap className={`w-3.5 h-3.5 ${valueOnly ? "fill-slate-900" : ""}`} /> Value
          {valueCount > 0 && <span className={`ml-0.5 tabular-nums ${valueOnly ? "text-slate-900" : "text-amber-400"}`}>{valueCount}</span>}
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-64 rounded-xl bg-slate-800/50" />)}
        </div>
      ) : matchs.length === 0 ? (
        <div className="card-surface rounded-xl p-10 text-center" data-testid="no-matches">
          <CalendarDays className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <div className="font-head text-xl font-bold text-slate-200">Aucun match ce jour</div>
          <p className="text-slate-500 text-sm mt-1">
            {nextDate || prevDate ? "Aller à la journée la plus proche :"
              : `Essayez une autre date${status?.matchs_en_base ? "" : " une fois les données synchronisées"}.`}
          </p>
          {(nextDate || prevDate) && (
            <div className="flex flex-wrap items-center justify-center gap-2 mt-4">
              {prevDate && (
                <Button variant="outline" onClick={() => setDate(prevDate)} data-testid="goto-prev-matchday"
                  className="border-slate-700 capitalize">
                  <ChevronLeft className="w-4 h-4" /> {frDate(prevDate + "T12:00:00")}
                </Button>
              )}
              {nextDate && (
                <Button onClick={() => setDate(nextDate)} data-testid="goto-next-matchday"
                  className="bg-emerald-500 hover:bg-emerald-600 text-white capitalize">
                  {frDate(nextDate + "T12:00:00")} <ChevronRight className="w-4 h-4" />
                </Button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="matches-grid">
          {matchs.map((m, i) => <MatchCard key={m.match_id} match={m} index={i} />)}
        </div>
      )}
    </div>
  );
}
