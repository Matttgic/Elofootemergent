import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { MatchCard } from "../components/MatchCard";
import { frDate, frDateShort, todayISO } from "../lib/format";
import { Skeleton } from "../components/ui/skeleton";
import { ChevronLeft, ChevronRight, CalendarDays, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "../components/ui/button";
import { motion } from "framer-motion";

function SyncBanner({ status, onRefresh, refreshing }) {
  if (!status) return null;
  if (!status.token_present) {
    return (
      <div className="card-surface rounded-xl p-5 border-amber-500/30 bg-amber-500/5 mb-6" data-testid="sync-banner-token">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-sm text-slate-300">
            <b className="text-amber-300">Clé API football-data.org requise.</b> Les données réelles
            (matchs, résultats, classements) seront chargées dès que la clé sera configurée.
            Aucune donnée fictive n'est affichée.
          </div>
        </div>
      </div>
    );
  }
  if (status.matchs_en_base === 0) {
    return (
      <div className="card-surface rounded-xl p-5 mb-6" data-testid="sync-banner-loading">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-5 h-5 text-emerald-400 shrink-0 animate-spin" />
          <div className="text-sm text-slate-300 flex-1">
            Synchronisation initiale des données en cours… Cela peut prendre 1 à 2 minutes.
          </div>
          <Button size="sm" variant="outline" onClick={onRefresh} disabled={refreshing}
            data-testid="btn-refresh-sync" className="border-slate-700">
            {refreshing ? "…" : "Actualiser"}
          </Button>
        </div>
      </div>
    );
  }
  return null;
}

export default function Home() {
  const [status, setStatus] = useState(null);
  const [comps, setComps] = useState([]);
  const [code, setCode] = useState(null);
  const [date, setDate] = useState(todayISO());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadStatus = useCallback(() => {
    api.get("/status").then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    loadStatus();
    api.get("/competitions").then((r) => setComps(r.data)).catch(() => {});
  }, [loadStatus]);

  useEffect(() => {
    setLoading(true);
    const params = { date };
    if (code) params.code = code;
    api.get("/matches", { params })
      .then((r) => setData(r.data))
      .catch(() => setData({ matchs: [] }))
      .finally(() => setLoading(false));
  }, [code, date]);

  const shiftDay = (delta) => {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + delta);
    setDate(d.toLocaleDateString("en-CA"));
  };

  const refresh = () => {
    setRefreshing(true);
    api.post("/admin/ingest").finally(() => {
      setRefreshing(false);
      loadStatus();
      setData(null);
      setLoading(true);
      const params = { date };
      if (code) params.code = code;
      api.get("/matches", { params }).then((r) => setData(r.data)).finally(() => setLoading(false));
    });
  };

  const matchs = data?.matchs || [];

  return (
    <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-6">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <h1 className="font-head text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-slate-50">
          Matchs & Analyse
        </h1>
        <p className="text-slate-400 text-sm sm:text-base mt-1">
          Notation statistique sur 100 des équipes des grands championnats européens.
        </p>
      </motion.div>

      <SyncBanner status={status} onRefresh={refresh} refreshing={refreshing} />

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

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-64 rounded-xl bg-slate-800/50" />)}
        </div>
      ) : matchs.length === 0 ? (
        <div className="card-surface rounded-xl p-10 text-center" data-testid="no-matches">
          <CalendarDays className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <div className="font-head text-xl font-bold text-slate-200">Aucun match ce jour</div>
          <p className="text-slate-500 text-sm mt-1">
            Essayez une autre date{status?.matchs_en_base ? "" : " une fois les données synchronisées"}.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="matches-grid">
          {matchs.map((m, i) => <MatchCard key={m.match_id} match={m} index={i} />)}
        </div>
      )}
    </div>
  );
}
