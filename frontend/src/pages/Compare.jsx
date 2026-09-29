import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { ProbabilityBar } from "../components/Probabilities";
import { FormChips } from "../components/FormChips";
import { Skeleton } from "../components/ui/skeleton";
import { frDate, frDateShort } from "../lib/format";
import { GitCompareArrows, History } from "lucide-react";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";

const COLORS = { a: "#10B981", b: "#06B6D4" };

function TeamSelect({ value, onChange, teams, testid }) {
  const groups = useMemo(() => {
    const g = {};
    teams.forEach((t) => { (g[t.competition_nom] = g[t.competition_nom] || []).push(t); });
    return Object.entries(g);
  }, [teams]);
  return (
    <select value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid={testid}
      className="w-full h-10 rounded-lg bg-slate-900/60 border border-slate-700 text-slate-100 text-sm px-2">
      {groups.map(([comp, list]) => (
        <optgroup key={comp} label={comp}>
          {list.map((t) => (
            <option key={`${t.competition_code}-${t.team_id}`} value={`${t.competition_code}-${t.team_id}`}>
              {t.nom_court || t.nom}{t.elo ? ` (${t.elo})` : ""}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

function TeamHeader({ t, color }) {
  return (
    <Link to={`/equipe/${t.competition_code}/${t.team_id}`} className="card-surface rounded-xl p-4 flex flex-col items-center text-center gap-1.5">
      {t.logo ? <img src={t.logo} alt="" className="w-12 h-12 object-contain" /> : <div className="w-12 h-12 rounded bg-slate-800" />}
      <div className="font-head font-bold text-slate-50 leading-tight">{t.nom_court || t.nom}</div>
      <div className="text-[11px] text-slate-500">{t.competition_nom}</div>
      {t.elo && (
        <div className="mt-1">
          <span className="font-stat font-black text-2xl" style={{ color }}>{t.elo.elo}</span>
          <div className="text-[10px] text-slate-500">ELO{t.elo.rang ? ` · rang ${t.elo.rang}/${t.elo.sur}` : ""}</div>
        </div>
      )}
    </Link>
  );
}

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const [teams, setTeams] = useState([]);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);
  const a = params.get("a");
  const b = params.get("b");

  useEffect(() => {
    api.get("/leaderboard/teams", { params: { tri: "elo" } }).then((r) => setTeams(r.data)).catch(() => setTeams([]));
  }, []);

  // Par défaut : les deux meilleurs Elo (ou l'équipe fournie face au meilleur Elo)
  useEffect(() => {
    if (!teams.length || (a && b)) return;
    const keys = teams.map((t) => `${t.competition_code}-${t.team_id}`);
    const first = a || keys[0];
    const second = b || keys.find((k) => k !== first);
    setParams({ a: first, b: second }, { replace: true });
  }, [teams, a, b, setParams]);

  useEffect(() => {
    if (!a || !b) return;
    setLoading(true);
    api.get("/compare", { params: { a, b } }).then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
  }, [a, b]);

  const radar = d ? ["global", "offensif", "defensif", "forme"].map((k) => ({
    stat: { global: "Global", offensif: "Attaque", defensif: "Défense", forme: "Forme" }[k],
    a: d.a[k] ?? 0, b: d.b[k] ?? 0,
  })) : [];

  const eloSeries = useMemo(() => {
    if (!d) return [];
    const byDate = {};
    [["a", d.a.elo_historique], ["b", d.b.elo_historique]].forEach(([k, list]) => {
      (list || []).forEach((p) => {
        const day = p.date.slice(0, 10);
        byDate[day] = { ...(byDate[day] || { date: day }), [k]: p.elo };
      });
    });
    return Object.values(byDate).sort((x, y) => x.date.localeCompare(y.date));
  }, [d]);

  const statRows = d ? [
    ["Buts / match", d.a.stats?.buts_par_match, d.b.stats?.buts_par_match, true],
    ["Encaissés / match", d.a.stats?.encaisses_par_match, d.b.stats?.encaisses_par_match, false],
    ["Cages inviolées", d.a.stats?.clean_sheets, d.b.stats?.clean_sheets, true],
    ["Note /100", d.a.global, d.b.global, true],
    ["Classement", d.a.classement?.position, d.b.classement?.position, false],
  ] : [];

  const nameA = d?.a.nom_court || "A", nameB = d?.b.nom_court || "B";

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-6">
      <h1 className="font-head text-3xl sm:text-4xl font-extrabold text-slate-50 mb-1 flex items-center gap-2">
        <GitCompareArrows className="w-7 h-7 text-emerald-400" /> Comparer
      </h1>
      <p className="text-slate-400 text-sm mb-5">Deux équipes côte à côte, même de championnats différents (l'Elo est comparable grâce aux coupes d'Europe).</p>

      <div className="grid grid-cols-2 gap-3 mb-5">
        <TeamSelect value={a} teams={teams} testid="compare-select-a" onChange={(v) => setParams({ a: v, b })} />
        <TeamSelect value={b} teams={teams} testid="compare-select-b" onChange={(v) => setParams({ a, b: v })} />
      </div>

      {loading || !d ? (
        <div className="space-y-3"><Skeleton className="h-40 rounded-xl bg-slate-800/50" /><Skeleton className="h-40 rounded-xl bg-slate-800/50" /></div>
      ) : (
        <div className="space-y-4" data-testid="compare-result">
          <div className="grid grid-cols-2 gap-3">
            <TeamHeader t={d.a} color={COLORS.a} />
            <TeamHeader t={d.b} color={COLORS.b} />
          </div>

          <div className="card-surface rounded-xl p-5 space-y-4" data-testid="compare-probas">
            <h3 className="font-head font-bold text-slate-100">Probabilités selon le terrain (modèle Elo)</h3>
            {[["a_recoit", nameA, nameB], ["b_recoit", nameB, nameA]].map(([k, home, away]) => (
              <div key={k}>
                <div className="text-xs text-slate-400 mb-1.5">Si <b className="text-slate-200">{home}</b> reçoit {away}</div>
                <ProbabilityBar pred={d[k]} homeName={home} awayName={away} testid={`compare-${k}`} />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card-surface rounded-xl p-5">
              <h3 className="font-head font-bold text-slate-100 mb-2">Notes /100 (10 derniers matchs)</h3>
              <ResponsiveContainer width="100%" height={260}>
                <RadarChart data={radar} outerRadius="70%">
                  <PolarGrid stroke="#334155" />
                  <PolarAngleAxis dataKey="stat" tick={{ fill: "#94A3B8", fontSize: 12 }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tickCount={5} tick={{ fill: "#475569", fontSize: 9 }} axisLine={false} />
                  <Radar name={nameA} dataKey="a" stroke={COLORS.a} fill={COLORS.a} fillOpacity={0.35} isAnimationActive={false} />
                  <Radar name={nameB} dataKey="b" stroke={COLORS.b} fill={COLORS.b} fillOpacity={0.3} isAnimationActive={false} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="card-surface rounded-xl p-5" data-testid="compare-stats">
              <h3 className="font-head font-bold text-slate-100 mb-3">Statistiques</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase text-slate-500 border-b border-slate-800">
                    <th className="py-1.5 text-left font-normal"></th>
                    <th className="py-1.5 text-right" style={{ color: COLORS.a }}>{nameA}</th>
                    <th className="py-1.5 text-right" style={{ color: COLORS.b }}>{nameB}</th>
                  </tr>
                </thead>
                <tbody>
                  {statRows.map(([label, va, vb, higherBetter]) => {
                    const best = va == null || vb == null || va === vb ? null : ((va > vb) === higherBetter ? "a" : "b");
                    return (
                      <tr key={label} className="border-b border-slate-800/60">
                        <td className="py-1.5 text-slate-400">{label}</td>
                        <td className={`py-1.5 text-right font-stat ${best === "a" ? "text-slate-50 font-bold" : "text-slate-400"}`}>{va ?? "—"}</td>
                        <td className={`py-1.5 text-right font-stat ${best === "b" ? "text-slate-50 font-bold" : "text-slate-400"}`}>{vb ?? "—"}</td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td className="py-2 text-slate-400">Forme</td>
                    <td className="py-2"><div className="flex justify-end"><FormChips form={d.a.forme_recente} /></div></td>
                    <td className="py-2"><div className="flex justify-end"><FormChips form={d.b.forme_recente} /></div></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {eloSeries.length > 1 && (
            <div className="card-surface rounded-xl p-5" data-testid="compare-elo-chart">
              <h3 className="font-head font-bold text-slate-100 mb-2">Évolution de l'Elo</h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={eloSeries}>
                  <CartesianGrid stroke="#1E293B" strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fill: "#64748B", fontSize: 11 }} tickFormatter={frDateShort} minTickGap={40} />
                  <YAxis domain={["dataMin - 20", "dataMax + 20"]} tick={{ fill: "#64748B", fontSize: 11 }}
                    tickFormatter={(v) => Math.round(v)} width={44} />
                  <Tooltip contentStyle={{ background: "#0B0E14", border: "1px solid #1E293B", borderRadius: 8, color: "#fff" }}
                    labelFormatter={(x) => frDate(x + "T12:00:00", true)} formatter={(v, k) => [Math.round(v), k === "a" ? nameA : nameB]} />
                  <Line type="monotone" dataKey="a" stroke={COLORS.a} strokeWidth={2} dot={false} connectNulls />
                  <Line type="monotone" dataKey="b" stroke={COLORS.b} strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {d.confrontations?.length > 0 && (
            <div className="card-surface rounded-xl p-4" data-testid="compare-h2h">
              <h3 className="font-head font-bold text-slate-100 mb-2 flex items-center gap-2"><History className="w-4 h-4 text-emerald-400" /> Confrontations directes</h3>
              {d.confrontations.map((c, i) => (
                <div key={i} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-800 last:border-0">
                  <span className="text-slate-500 text-xs w-24 shrink-0">{frDate(c.date, true)}</span>
                  <span className="text-slate-200 flex-1 text-right truncate">{c.domicile}</span>
                  <span className="font-stat font-bold text-slate-100 mx-3">{c.score}</span>
                  <span className="text-slate-200 flex-1 truncate">{c.exterieur}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
