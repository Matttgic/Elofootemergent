"""xG par match (Understat, 5 grands championnats) rattachés aux matchs football-data.

Un appel par championnat et par saison : la saison en cours à chaque synchro complète,
les HISTORY_SEASONS précédentes une seule fois. Le rapprochement se fait par équipes
(même correspondance de noms que pour les joueurs) et par date (± 1 jour, les deux
sources n'utilisant pas le même fuseau).
"""
import logging
from datetime import datetime, timezone

from pymongo import UpdateOne

from ingest import HISTORY_RETRY, HISTORY_SEASONS, configured_codes
from player_ingest import build_team_map, current_season
from understat_client import UNDERSTAT_LEAGUES, fetch_league_matches

logger = logging.getLogger(__name__)


def _day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00").replace(" ", "T")[:19]).date().toordinal()


def attach_xg_ops(us_matches, fd_matches):
    """Opérations d'écriture des xG pour les matchs football-data rapprochés.
    Retourne (ops, nombre de matchs Understat non rapprochés)."""
    teams = {}
    for m in fd_matches:
        for side in ("home_team", "away_team"):
            t = m.get(side) or {}
            # garder la fiche nommée (un match partiel peut n'avoir que l'identifiant)
            if t.get("id") is not None and (t.get("name") or t["id"] not in teams):
                teams[t["id"]] = t
    titles = {d["h"]["title"] for d in us_matches} | {d["a"]["title"] for d in us_matches}
    tmap = build_team_map(sorted(titles), list(teams.values()))
    index = {}
    for m in fd_matches:
        key = ((m.get("home_team") or {}).get("id"), (m.get("away_team") or {}).get("id"))
        index.setdefault(key, []).append((_day(m["utc_date"]), m["match_id"]))
    ops, missed = [], 0
    for d in us_matches:
        cands = index.get((tmap.get(d["h"]["title"]), tmap.get(d["a"]["title"])), [])
        day = _day(d["datetime"])
        mid = next((i for dd, i in cands if abs(dd - day) <= 1), None)
        if mid is None:
            missed += 1
            continue
        ops.append(UpdateOne({"match_id": mid}, {"$set": {"xg": {
            "home": round(float(d["xG"]["h"]), 3), "away": round(float(d["xG"]["a"]), 3), "source": "understat"}}}))
    return ops, missed


async def ingest_xg(db, now=None):
    """Rattache les xG Understat aux matchs (saison en cours + saisons précédentes)."""
    now = now or datetime.now(timezone.utc)
    season_now = current_season()
    done = ((await db.meta.find_one({"_id": "xg"})) or {}).get("saisons", {})
    stats = {"appels": 0, "rattaches": 0, "non_rattaches": 0}
    proj = {"_id": 0, "match_id": 1, "utc_date": 1, "home_team": 1, "away_team": 1}
    for code, league in UNDERSTAT_LEAGUES.items():
        if code not in configured_codes():
            continue
        for season in range(season_now, season_now - HISTORY_SEASONS - 1, -1):
            key = f"{code}-{season}"
            state = done.get(key) or {}
            if season != season_now and (state.get("statut") == "ok" or (
                    state.get("at") and now - datetime.fromisoformat(state["at"]) < HISTORY_RETRY)):
                continue
            if season == season_now:
                coll, q = db.matches, {"competition_code": code, "status": "FINISHED"}
            else:
                coll, q = db.matches_history, {"competition_code": code, "season": season, "status": "FINISHED"}
            fd_matches = await coll.find(q, proj).to_list(1000)
            if not fd_matches:
                continue
            try:
                us_matches = await fetch_league_matches(league, season)
            except Exception as e:  # noqa: BLE001
                logger.error("xG Understat %s échec : %s", key, e)
                await db.meta.update_one({"_id": "xg"}, {"$set": {f"saisons.{key}": {
                    "statut": "erreur", "at": now.isoformat()}}}, upsert=True)
                continue
            stats["appels"] += 1
            ops, missed = attach_xg_ops(us_matches, fd_matches)
            if ops:
                await coll.bulk_write(ops, ordered=False)
            stats["rattaches"] += len(ops)
            stats["non_rattaches"] += missed
            await db.meta.update_one({"_id": "xg"}, {"$set": {f"saisons.{key}": {
                "statut": "ok", "rattaches": len(ops), "non_rattaches": missed, "at": now.isoformat()}}}, upsert=True)
            logger.info("xG %s : %s matchs rattachés, %s non rattachés", key, len(ops), missed)
    return stats
