import { useState, useEffect, useCallback } from "react";

const KEY = "footpulse_fav_teams";

function read() {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

export function useFavorites() {
  const [favs, setFavs] = useState(read);

  useEffect(() => {
    const h = () => setFavs(read());
    window.addEventListener("storage", h);
    return () => window.removeEventListener("storage", h);
  }, []);

  const isFav = useCallback((id) => favs.some((f) => String(f.team_id) === String(id)), [favs]);

  const toggle = useCallback((team) => {
    setFavs((prev) => {
      const exists = prev.some((f) => String(f.team_id) === String(team.team_id));
      const next = exists ? prev.filter((f) => String(f.team_id) !== String(team.team_id)) : [...prev, team];
      localStorage.setItem(KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  return { favs, isFav, toggle };
}
