import { resultColor } from "../lib/format";

export function FormChips({ form, testid }) {
  if (!form || !form.length) return <span className="text-xs text-slate-500 font-stat">—</span>;
  return (
    <div className="flex items-center gap-1" data-testid={testid}>
      {form.map((r, i) => (
        <span
          key={i}
          className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold font-stat text-white"
          style={{ backgroundColor: resultColor(r) }}
          title={r === "W" ? "Victoire" : r === "D" ? "Nul" : "Défaite"}
        >
          {r === "W" ? "V" : r === "D" ? "N" : "D"}
        </span>
      ))}
    </div>
  );
}
