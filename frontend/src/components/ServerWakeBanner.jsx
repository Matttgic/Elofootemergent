import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { onSlowChange } from "../lib/api";

// Bandeau affiché quand l'API met du temps à répondre (réveil de l'hébergement gratuit).
export function ServerWakeBanner() {
  const [slow, setSlow] = useState(false);
  useEffect(() => onSlowChange(setSlow), []);
  if (!slow) return null;
  return (
    <div role="status" data-testid="server-wake-banner"
      className="fixed bottom-4 inset-x-4 sm:inset-x-auto sm:right-6 sm:max-w-sm z-50 card-surface rounded-xl px-4 py-3 flex items-start gap-3 shadow-lg border border-emerald-500/30">
      <Loader2 className="w-5 h-5 text-emerald-400 animate-spin shrink-0 mt-0.5" />
      <div className="text-sm leading-snug">
        <div className="font-semibold text-slate-100">Réveil du serveur…</div>
        <div className="text-slate-400 text-xs mt-0.5">
          L'hébergement gratuit se met en veille sans visite : le premier chargement peut prendre jusqu'à une minute.
        </div>
      </div>
    </div>
  );
}
