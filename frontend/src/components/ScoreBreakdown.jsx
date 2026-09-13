import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { scoreColor } from "../lib/format";
import { DataUnavailable } from "./DataUnavailable";
import { Info } from "lucide-react";

export function ScoreBreakdown({ data, title, team, children, testid }) {
  if (!data) return children;
  const color = scoreColor(data.score);
  return (
    <Dialog>
      <DialogTrigger asChild data-testid={testid}>{children}</DialogTrigger>
      <DialogContent className="bg-[#161C2E] border-slate-700 text-slate-100 max-w-md">
        <DialogHeader>
          <DialogTitle className="font-head text-xl flex items-center gap-2">
            <Info className="w-4 h-4 text-emerald-400" />
            {title} — {team}
          </DialogTitle>
        </DialogHeader>
        <div className="flex items-center gap-3 py-2">
          <div className="text-4xl font-black font-stat" style={{ color }}>{data.score}</div>
          <div className="text-slate-400 text-sm">/ 100<br />
            <span className="text-xs">Décomposition transparente du calcul</span>
          </div>
        </div>
        <div className="space-y-3">
          {data.composantes.map((c, i) => (
            <div key={i} className="border-b border-slate-800 pb-2 last:border-0">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-200">{c.libelle}</span>
                {c.indisponible
                  ? <DataUnavailable />
                  : <span className="text-sm font-bold font-stat text-emerald-400">+{c.contribution}</span>}
              </div>
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-xs text-slate-500">{c.detail}</span>
                <span className="text-xs text-slate-500 font-stat">pondération {c.poids}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-2">
          La somme des contributions donne le score final. Les matchs récents et le niveau des adversaires
          sont pris en compte.
        </p>
      </DialogContent>
    </Dialog>
  );
}
