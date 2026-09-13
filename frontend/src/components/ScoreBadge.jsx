import { scoreColor } from "../lib/format";
import { DataUnavailable } from "./DataUnavailable";

export function ScoreBadge({ score, size = "md", testid }) {
  if (score === null || score === undefined) return <DataUnavailable />;
  const color = scoreColor(score);
  const dims = size === "lg" ? "w-16 h-16 text-2xl" : size === "sm" ? "w-10 h-10 text-sm" : "w-12 h-12 text-lg";
  return (
    <div
      data-testid={testid}
      className={`${dims} rounded-full flex items-center justify-center font-black font-stat shrink-0`}
      style={{ color, backgroundColor: `${color}1A`, border: `2px solid ${color}55` }}
    >
      {score}
    </div>
  );
}
