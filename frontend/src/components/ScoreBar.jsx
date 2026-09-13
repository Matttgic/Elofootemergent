import { scoreColor } from "../lib/format";
import { DataUnavailable } from "./DataUnavailable";

export function ScoreBar({ label, score, onClick, testid }) {
  const color = scoreColor(score);
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className="w-full text-left group"
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-400 font-medium group-hover:text-slate-200 transition-colors">{label}</span>
        {score === null || score === undefined
          ? <DataUnavailable />
          : <span className="text-sm font-bold font-stat" style={{ color }}>{score}</span>}
      </div>
      <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500"
             style={{ width: `${score ?? 0}%`, backgroundColor: color }} />
      </div>
    </button>
  );
}
