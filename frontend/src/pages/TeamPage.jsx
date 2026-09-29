import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { ScoreBadge } from "../components/ScoreBadge";
import { ScoreBar } from "../components/ScoreBar";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { DataUnavailable } from "../components/DataUnavailable";
import { FormChips } from "../components/FormChips";
import { frDate, frDateShort, resultColor, scoreColor } from "../lib/format";
import { Skeleton } from "../components/ui/skeleton";
import { ArrowLeft, GitCompareArrows } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export default function TeamPage() {
  const { code, id } = useParams();
  const [t, setT] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/team/${code}/${id}`).then((r) => setT(r.data)).catch(() => setT(null)).finally(() => setLoading(false));
  }, [code, id]);

  if (loading) return <div className="max-w-4xl mx-auto px-4 py-6 space-y-4"><Skeleton className="h-32 rounded-xl bg-slate-800/50" /><Skeleton className="h-64 rounded-xl bg-slate-800/50" /></div>;
  if (!t) return <div className="max-w-4xl mx-auto px-4 py-10 text-center text-slate-400">Équipe introuvable.</div>;

  const evo = [...(t.historique || [])].reverse().map((h, i) => ({ n: i + 1, score: h.score_obtenu, adv: h.adversaire }));
  const eloEvo = (t.elo_historique || []).map((p) => ({ date: p.date.slice(0, 10), elo: p.elo }));

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-6">
      <Link to="/classements" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-emerald-400 mb-4">
        <ArrowLeft className="w-4 h-4" /> Retour
      </Link>

      <div className="card-surface rounded-xl p-5 mb-6">
        <div className="flex items-center gap-4">
          {t.logo ? <img src={t.logo} alt="" className="w-16 h-16 object-contain" /> : <div className="w-16 h-16 rounded bg-slate-800" />}
          <div className="flex-1 min-w-0">
            <h1 className="font-head text-2xl font-extrabold text-slate-50 truncate">{t.nom}</h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <FormChips form={t.stats?.forme_recente} />
              {t.classement && <span className="text-xs text-slate-400 font-stat">Classement {t.classement.position}e · {t.classement.points} pts</span>}
            </div>
            <Link to={`/comparer?a=${code}-${t.team_id}`} data-testid="team-compare-link"
              className="inline-flex items-center gap-1 mt-2 text-xs text-emerald-400 hover:text-emerald-300">
              <GitCompareArrows className="w-3.5 h-3.5" /> Comparer avec une autre équipe
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 sm:gap-3 mt-5">
          {t.elo ? (
            <div className="rounded-lg bg-emerald-500/10 ring-1 ring-emerald-500/40 p-3" data-testid="team-elo">
              <div className="text-[10px] uppercase tracking-wide text-emerald-300 font-semibold">Force Elo</div>
              <div className="font-stat font-black text-2xl sm:text-3xl text-slate-50 leading-tight">{t.elo.elo}</div>
              <div className="text-[11px] text-slate-400">
                {t.elo.rang ? <>{t.elo.rang}<sup>e</sup> sur {t.elo.sur} · {t.elo.championnat_nom || t.elo.championnat}</> : `${t.elo.matchs} matchs notés`}
              </div>
            </div>
          ) : <div />}
          <div className="rounded-lg bg-slate-900/50 p-3" data-testid="team-xg">
            <div className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Forme xG</div>
            <div className="font-stat font-black text-2xl sm:text-3xl text-slate-100 leading-tight">
              {t.elo?.forme_xg != null ? `${t.elo.forme_xg > 0 ? "+" : ""}${t.elo.forme_xg.toFixed(2).replace(".", ",")}` : "—"}
            </div>
            <div className="text-[11px] text-slate-500">{t.elo?.forme_xg != null ? "xG créés − concédés / match" : "xG indisponibles"}</div>
          </div>
          <ScoreBreakdown data={t.global} title="Note de forme" team={t.nom_court}>
            <button className="rounded-lg bg-slate-900/50 p-3 text-left" data-testid="team-form-note">
              <div className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">Forme /100</div>
              <div className="font-stat font-black text-2xl sm:text-3xl leading-tight" style={{ color: scoreColor(t.global?.score ?? 0) }}>
                {t.global?.score ?? "—"}
              </div>
              <div className="text-[11px] text-slate-500 underline decoration-dotted underline-offset-2">10 derniers matchs · détail</div>
            </button>
          </ScoreBreakdown>
        </div>
        <p className="mt-3 text-[11px] text-slate-500">
          Le pronostic des matchs s'appuie sur la force Elo et la forme xG ; la note de forme /100 est un résumé descriptif.
        </p>
      </div>

      {eloEvo.length > 1 && (
        <div className="card-surface rounded-xl p-5 mb-6" data-testid="team-elo-chart">
          <h3 className="font-head font-bold text-slate-100 mb-2">Évolution de la force Elo</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={eloEvo}>
              <CartesianGrid stroke="#1E293B" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#64748B", fontSize: 11 }} tickFormatter={frDateShort} minTickGap={40} />
              <YAxis domain={["dataMin - 20", "dataMax + 20"]} tick={{ fill: "#64748B", fontSize: 11 }}
                tickFormatter={(v) => Math.round(v)} width={44} />
              <Tooltip contentStyle={{ background: "#0B0E14", border: "1px solid #1E293B", borderRadius: 8, color: "#fff" }}
                labelFormatter={(d) => frDate(d + "T12:00:00", true)} formatter={(v) => [Math.round(v), "Elo"]} />
              <Line type="monotone" dataKey="elo" stroke="#10B981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <h3 className="font-head font-bold text-slate-100 mb-2">Note de forme /100 · détail</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        {[["offensif", "Attaque"], ["defensif", "Défense"], ["forme", "Résultats"]].map(([k, label]) => (
          <div key={k} className="card-surface rounded-xl p-4">
            <ScoreBreakdown data={t[k]} title={label} team={t.nom_court}>
              <div><ScoreBar label={`${label} · détail`} score={t[k]?.score} /></div>
            </ScoreBreakdown>
          </div>
        ))}
      </div>

      {t.stats && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-6">
          {[["Matchs", t.stats.matchs_analyses], ["V", t.stats.victoires], ["N", t.stats.nuls], ["D", t.stats.defaites], ["Buts", t.stats.buts_marques], ["Encaissés", t.stats.buts_encaisses]].map(([l, v]) => (
            <div key={l} className="card-surface rounded-lg p-3 text-center">
              <div className="font-stat font-bold text-slate-100">{v}</div>
              <div className="text-[10px] text-slate-500 uppercase">{l}</div>
            </div>
          ))}
        </div>
      )}

      {evo.length > 1 && (
        <div className="card-surface rounded-xl p-5 mb-6">
          <h3 className="font-head font-bold text-slate-100 mb-2">Performance match par match (/100)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={evo}>
              <CartesianGrid stroke="#1E293B" vertical={false} />
              <XAxis dataKey="n" tick={{ fill: "#64748B", fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fill: "#64748B", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#0B0E14", border: "1px solid #1E293B", borderRadius: 8, color: "#fff" }}
                labelFormatter={(n) => `Match ${n}`} formatter={(v, _, p) => [`${v}/100`, p.payload.adv]} />
              <Line type="monotone" dataKey="score" stroke="#10B981" strokeWidth={2} dot={{ r: 3, fill: "#10B981" }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <h3 className="font-head font-bold text-slate-100 mb-2">Derniers matchs</h3>
      <div className="card-surface rounded-xl overflow-hidden" data-testid="team-history">
        {(t.historique || []).map((h, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-slate-800 last:border-0 text-sm">
            <span className="w-16 text-xs text-slate-500 shrink-0">{frDate(h.date)}</span>
            <span className="w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold text-white shrink-0" style={{ backgroundColor: resultColor(h.resultat) }}>
              {h.resultat === "W" ? "V" : h.resultat === "D" ? "N" : "D"}
            </span>
            <span className="text-slate-500 text-xs w-12 shrink-0">{h.lieu === "Domicile" ? "Dom." : "Ext."}</span>
            <span className="text-slate-200 flex-1 truncate">{h.adversaire}</span>
            <span className="font-stat font-bold text-slate-100">{h.buts_marques}-{h.buts_encaisses}</span>
            <ScoreBadge score={h.score_obtenu} size="sm" />
          </div>
        ))}
      </div>
    </div>
  );
}
