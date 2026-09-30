"""xG par match rattachés aux matchs football-data.

- Understat (5 grands championnats) : un appel par championnat et par saison.
- FotMob (Portugal, Pays-Bas, Championship, Brésil) : la liste des matchs d'une saison,
  puis un appel par match encore sans xG, dans la limite d'un budget par synchro (le
  rattrapage des saisons précédentes s'étale sur quelques synchros).

La saison en cours est relue à chaque synchro complète, les HISTORY_SEASONS précédentes
jusqu'à ce qu'elles soient complètes. Le rapprochement se fait d'abord par les résultats
(même jour ± 1, même score) pour apprendre la correspondance des noms d'équipes, puis
par la ressemblance des noms ; enfin par équipes et date (± 1 jour, les sources n'ayant
pas le même fuseau).
"""
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

from pymongo import UpdateOne

from fotmob_client import (FOTMOB_XG_LEAGUES, CALENDAR_YEAR_LEAGUES, fetch_finished_fixtures,
                           fetch_matches_xg, fotmob_client, fotmob_season)
from ingest import HISTORY_RETRY, HISTORY_SEASONS, configured_codes
from player_ingest import _sim, build_team_map, current_season
from understat_client import UNDERSTAT_LEAGUES, fetch_league_matches

logger = logging.getLogger(__name__)

FOTMOB_BUDGET = 1500        # fiches de match FotMob lues au plus par synchro complète


def _day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00").replace(" ", "T")[:19]).date().toordinal()


def _fd_score(m):
    ft = (m.get("score") or {}).get("fullTime") or {}
    return (ft["home"], ft["away"]) if ft.get("home") is not None and ft.get("away") is not None else None


def _team_name(t):
    return t.get("name") or t.get("shortName") or ""


def team_map(fixtures, fd_matches):
    """{nom d'équipe de la source: team_id football-data}. D'abord appris sur les
    résultats : chaque match de la source vote pour le match football-data du même jour
    (± 1) au même score dont les noms ressemblent le plus ; les couples les plus votés
    sont retenus, une équipe au plus par nom. Les noms restants : ressemblance seule."""
    teams = {}
    for m in fd_matches:
        for side in ("home_team", "away_team"):
            t = m.get(side) or {}
            # garder la fiche nommée (un match partiel peut n'avoir que l'identifiant)
            if t.get("id") is not None and (t.get("name") or t["id"] not in teams):
                teams[t["id"]] = t
    by_day = defaultdict(list)
    for m in fd_matches:
        if _fd_score(m) is not None and m.get("utc_date"):
            by_day[_day(m["utc_date"])].append(m)
    votes = Counter()
    for fx in fixtures:
        if not fx.get("score"):
            continue
        d = _day(fx["utc"])
        cands = [m for dd in (d - 1, d, d + 1) for m in by_day.get(dd, []) if _fd_score(m) == tuple(fx["score"])]
        if not cands:
            continue
        best = max(cands, key=lambda m: _sim(fx["home"], _team_name(teams.get(m["home_team"]["id"], m["home_team"])))
                   + _sim(fx["away"], _team_name(teams.get(m["away_team"]["id"], m["away_team"]))))
        votes[(fx["home"], best["home_team"]["id"])] += 1
        votes[(fx["away"], best["away_team"]["id"])] += 1
    mapping, used = {}, set()
    for (name, tid), n in votes.most_common():
        if n >= 2 and name not in mapping and tid not in used:
            mapping[name] = tid
            used.add(tid)
    rest = sorted(({f["home"] for f in fixtures} | {f["away"] for f in fixtures}) - set(mapping))
    free = [t for i, t in teams.items() if i not in used]
    if rest and free:
        for name, tid in build_team_map(rest, free).items():
            mapping.setdefault(name, tid)
    return mapping


def pair_fixtures(fixtures, fd_matches):
    """([(match de la source, match_id football-data)], nombre de matchs non rapprochés)."""
    tmap = team_map(fixtures, fd_matches)
    index = {}
    for m in fd_matches:
        key = ((m.get("home_team") or {}).get("id"), (m.get("away_team") or {}).get("id"))
        index.setdefault(key, []).append((_day(m["utc_date"]), m["match_id"]))
    pairs, missed = [], 0
    for fx in fixtures:
        cands = index.get((tmap.get(fx["home"]), tmap.get(fx["away"])), [])
        day = _day(fx["utc"])
        mid = next((i for dd, i in cands if abs(dd - day) <= 1), None)
        if mid is None:
            missed += 1
        else:
            pairs.append((fx, mid))
    return pairs, missed


def _xg_op(mid, xg, source):
    doc = ({"home": round(float(xg[0]), 3), "away": round(float(xg[1]), 3), "source": source} if xg
           else {"source": source, "absent": True})       # la source n'a pas d'xG pour ce match
    return UpdateOne({"match_id": mid}, {"$set": {"xg": doc}})


def _understat_fixture(d):
    goals = d.get("goals") or {}
    try:
        score = (int(goals["h"]), int(goals["a"]))
    except (KeyError, TypeError, ValueError):
        score = None
    return {"home": d["h"]["title"], "away": d["a"]["title"], "utc": d["datetime"], "score": score,
            "xg": (float(d["xG"]["h"]), float(d["xG"]["a"]))}


def attach_xg_ops(us_matches, fd_matches):
    """Opérations d'écriture des xG Understat pour les matchs football-data rapprochés.
    Retourne (ops, nombre de matchs Understat non rapprochés)."""
    pairs, missed = pair_fixtures([_understat_fixture(d) for d in us_matches], fd_matches)
    return [_xg_op(mid, fx["xg"], "understat") for fx, mid in pairs], missed


def _skip_history(state, now):
    """Saison précédente déjà complète, ou en erreur récente (nouvel essai plus tard)."""
    return state.get("statut") == "ok" or (
        state.get("statut") == "erreur" and state.get("at") and now - datetime.fromisoformat(state["at"]) < HISTORY_RETRY)


async def ingest_xg(db, now=None):
    """Rattache les xG aux matchs : Understat (5 grands championnats), puis FotMob."""
    now = now or datetime.now(timezone.utc)
    stats = await _ingest_understat(db, now)
    try:
        stats["fotmob"] = await ingest_xg_fotmob(db, now)
    except Exception as e:  # noqa: BLE001
        logger.error("xG FotMob échec : %s", e)
        stats["fotmob"] = {"ok": False}
    return stats


PROJ = {"_id": 0, "match_id": 1, "utc_date": 1, "home_team": 1, "away_team": 1, "score.fullTime": 1, "xg": 1}


def _season_query(db, code, season, season_now):
    if season == season_now:
        return db.matches, {"competition_code": code, "status": "FINISHED"}
    return db.matches_history, {"competition_code": code, "season": season, "status": "FINISHED"}


async def _ingest_understat(db, now):
    season_now = current_season()
    done = ((await db.meta.find_one({"_id": "xg"})) or {}).get("saisons", {})
    stats = {"appels": 0, "rattaches": 0, "non_rattaches": 0}
    proj = PROJ
    for code, league in UNDERSTAT_LEAGUES.items():
        if code not in configured_codes():
            continue
        for season in range(season_now, season_now - HISTORY_SEASONS - 1, -1):
            key = f"{code}-{season}"
            state = done.get(key) or {}
            if season != season_now and (state.get("statut") == "ok" or (
                    state.get("at") and now - datetime.fromisoformat(state["at"]) < HISTORY_RETRY)):
                continue
            coll, q = _season_query(db, code, season, season_now)
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


async def ingest_xg_fotmob(db, now=None, budget=FOTMOB_BUDGET):
    """xG FotMob des championnats sans Understat : liste des matchs terminés de chaque
    saison, puis une fiche par match rapproché encore sans xG (au plus `budget` fiches
    par synchro). Une saison précédente est « ok » quand tous ses matchs sont traités."""
    now = now or datetime.now(timezone.utc)
    done = ((await db.meta.find_one({"_id": "xg"})) or {}).get("saisons", {})
    stats = {"appels": 0, "fiches": 0, "rattaches": 0, "sans_xg": 0, "non_rattaches": 0, "restant": 0}
    codes = [c for c in FOTMOB_XG_LEAGUES if c in configured_codes()]
    if not codes:
        return stats
    async with fotmob_client() as client:
        # saisons en cours de tous les championnats d'abord (elles servent aux pronostics),
        # puis les saisons précédentes, dans la limite du budget
        for offset in range(HISTORY_SEASONS + 1):
            for code in codes:
                # saison sur l'année civile au Brésil (la saison 2027 commence en avril 2027)
                season_now = now.year if code in CALENDAR_YEAR_LEAGUES else current_season()
                season = season_now - offset
                key = f"{code}-{season}"
                if season != season_now and _skip_history(done.get(key) or {}, now):
                    continue
                coll, q = _season_query(db, code, season, season_now)
                fd_matches = await coll.find(q, PROJ).to_list(1000)
                if not fd_matches:
                    continue
                try:
                    fixtures = await fetch_finished_fixtures(client, FOTMOB_XG_LEAGUES[code], fotmob_season(code, season))
                    stats["appels"] += 1
                except Exception as e:  # noqa: BLE001
                    logger.error("xG FotMob %s échec : %s", key, e)
                    await db.meta.update_one({"_id": "xg"}, {"$set": {f"saisons.{key}": {
                        "statut": "erreur", "source": "fotmob", "at": now.isoformat()}}}, upsert=True)
                    continue
                pairs, missed = pair_fixtures(fixtures, fd_matches)
                have = {m["match_id"] for m in fd_matches if m.get("xg")}
                todo = [(fx, mid) for fx, mid in pairs if mid not in have]
                take = todo[:max(budget - stats["fiches"], 0)]
                xgs = await fetch_matches_xg(client, [fx["id"] for fx, _ in take]) if take else {}
                stats["fiches"] += len(take)
                ops = [_xg_op(mid, xgs[fx["id"]], "fotmob") for fx, mid in take if fx["id"] in xgs]
                if ops:
                    await coll.bulk_write(ops, ordered=False)
                n_xg = sum(1 for fx, _ in take if xgs.get(fx["id"]))
                remaining = len(todo) - len(ops)
                stats["rattaches"] += n_xg
                stats["sans_xg"] += len(ops) - n_xg
                stats["non_rattaches"] += missed
                stats["restant"] += remaining
                await db.meta.update_one({"_id": "xg"}, {"$set": {f"saisons.{key}": {
                    "statut": "ok" if remaining == 0 else "partiel", "source": "fotmob",
                    "rattaches": len(have) + n_xg, "non_rattaches": missed, "restant": remaining,
                    "at": now.isoformat()}}}, upsert=True)
                logger.info("xG FotMob %s : %s nouveaux, %s restants, %s non rapprochés", key, n_xg, remaining, missed)
    return stats
