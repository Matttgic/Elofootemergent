"""Ingestion des joueurs Understat + rapprochement des équipes avec football-data."""
import logging
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher

from understat_client import fetch_players, UNDERSTAT_LEAGUES
from fotmob_client import fetch_league_players, FOTMOB_LEAGUES, fotmob_poste

logger = logging.getLogger(__name__)

_STOP = {"fc", "cf", "ac", "as", "sc", "ss", "rc", "cd", "sv", "vfl", "vfb", "tsg", "sd",
         "club", "de", "the", "calcio", "balompie", "ud", "afc", "bc", "us", "1899", "04",
         "05", "09", "1913", "1846", "1904", "1907", "1900", "hsv"}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    toks = [t for t in s.split() if t and t not in _STOP]
    return " ".join(toks)


# Rares cas où le rapprochement flou échoue (nom trop différent d'une source à l'autre)
ALIASES = {
    "FC Cologne": "Koln",
    "Paris Saint Germain": "Paris",
    "Wolverhampton Wanderers": "Wolverhampton",
    "Athletic Club": "Athletic Bilbao",
}


def _sim(a, b):
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    jacc = len(ta & tb) / len(ta | tb) if (ta | tb) else 0
    ratio = SequenceMatcher(None, na, nb).ratio()
    contains = 1.0 if (na in nb or nb in na) else 0.0
    return max(jacc, ratio, contains * 0.9)


def build_team_map(understat_titles, fd_teams):
    """Associe chaque titre d'équipe Understat à un team_id football-data."""
    mapping, unmatched = {}, []
    for title in understat_titles:
        candidates = [title]
        if title in ALIASES:
            candidates.append(ALIASES[title])
        best_id, best_score = None, 0.0
        for t in fd_teams:
            for name in (t.get("name"), t.get("shortName"), t.get("tla")):
                sc = max(_sim(cand, name) for cand in candidates)
                if sc > best_score:
                    best_score, best_id = sc, t.get("id")
        if best_id is not None and best_score >= 0.5:
            mapping[title] = best_id
        else:
            unmatched.append(title)
    if unmatched:
        logger.info("Understat équipes non rapprochées: %s", unmatched)
    return mapping


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def current_season():
    n = datetime.now(timezone.utc)
    return n.year if n.month >= 7 else n.year - 1


async def ingest_players(db):
    season = current_season()
    now = datetime.now(timezone.utc).isoformat()
    total = 0
    for code, league_key in UNDERSTAT_LEAGUES.items():
        try:
            players = await fetch_players(league_key, season)
        except Exception as e:  # noqa: BLE001
            logger.error("Understat échec %s: %s", league_key, e)
            continue

        fd_docs = await db.matches.find(
            {"competition_code": code}, {"_id": 0, "home_team": 1, "away_team": 1}).to_list(2000)
        fd_teams = {}
        for d in fd_docs:
            for side in ("home_team", "away_team"):
                t = d.get(side) or {}
                if t.get("id") is not None:
                    fd_teams[t["id"]] = t
        titles = {p.get("team_title") for p in players if p.get("team_title")}
        tmap = build_team_map(titles, list(fd_teams.values()))

        docs = []
        for p in players:
            docs.append({
                "player_id": str(p.get("id")),
                "competition_code": code,
                "season": season,
                "nom": p.get("player_name"),
                "position": p.get("position"),
                "team_title": p.get("team_title"),
                "team_id": tmap.get(p.get("team_title")),
                "games": _i(p.get("games")),
                "minutes": _i(p.get("time")),
                "goals": _i(p.get("goals")),
                "assists": _i(p.get("assists")),
                "shots": _i(p.get("shots")),
                "key_passes": _i(p.get("key_passes")),
                "xG": _f(p.get("xG")),
                "xA": _f(p.get("xA")),
                "npg": _i(p.get("npg")),
                "npxG": _f(p.get("npxG")),
                "xGChain": _f(p.get("xGChain")),
                "xGBuildup": _f(p.get("xGBuildup")),
                "yellow": _i(p.get("yellow_cards")),
                "red": _i(p.get("red_cards")),
                "last_synced_at": now,
            })

        await db.players.delete_many({"competition_code": code})
        if docs:
            await db.players.insert_many(docs)
        total += len(docs)
        logger.info("Joueurs %s: %s (équipes rapprochées %s/%s)", code, len(docs), len(tmap), len(titles))

    await db.meta.update_one({"_id": "sync_players"},
                             {"$set": {"_id": "sync_players", "last_sync": now, "joueurs": total, "saison": season}},
                             upsert=True)
    return {"ok": True, "joueurs": total, "saison": season}



async def ingest_fotmob_players(db):
    """Ingestion des joueurs FotMob pour les ligues non couvertes par Understat
    (Portugal, Pays-Bas). Schéma identique aux docs Understat pour réutiliser la
    même notation. Aucune donnée n'est inventée."""
    now = datetime.now(timezone.utc).isoformat()
    total = 0
    for code, lid in FOTMOB_LEAGUES.items():
        st = await db.standings.find_one({"competition_code": code}, {"_id": 0, "season": 1})
        target_name = None
        start = ((st or {}).get("season") or {}).get("startDate")
        if start:
            y = int(start[:4])
            target_name = f"{y}/{y + 1}"
        try:
            sid, sname, players = await fetch_league_players(lid, target_name)
        except Exception as e:  # noqa: BLE001
            logger.error("FotMob échec %s: %s", code, e)
            continue

        fd_docs = await db.matches.find(
            {"competition_code": code}, {"_id": 0, "home_team": 1, "away_team": 1}).to_list(2000)
        fd_teams = {}
        for d in fd_docs:
            for side in ("home_team", "away_team"):
                t = d.get(side) or {}
                if t.get("id") is not None:
                    fd_teams[t["id"]] = t
        titles = {p.get("team_title") for p in players if p.get("team_title")}
        tmap = build_team_map(titles, list(fd_teams.values()))

        docs = []
        for p in players:
            if not p.get("minutes"):
                continue
            xg = _f(p.get("xG"))
            xa = _f(p.get("xA"))
            docs.append({
                "player_id": f"fm{p['id']}",
                "competition_code": code,
                "season": sid,
                "source": "fotmob",
                "nom": p.get("nom"),
                "position": fotmob_poste(p.get("positions")),
                "team_title": p.get("team_title"),
                "team_id": tmap.get(p.get("team_title")),
                "games": _i(p.get("games")),
                "minutes": _i(p.get("minutes")),
                "goals": _i(p.get("goals")),
                "assists": _i(p.get("assists")),
                "shots": _i(p.get("shots")),
                "key_passes": _i(p.get("key_passes")),
                "xG": xg,
                "xA": xa,
                "xGChain": round(xg + xa, 2),   # proxy (FotMob ne fournit pas le xGChain)
                "yellow": _i(p.get("yellow")),
                "red": _i(p.get("red")),
                "last_synced_at": now,
            })

        # Ne pas écraser les données existantes si la récupération FotMob est vide
        if docs:
            await db.players.delete_many({"competition_code": code})
            await db.players.insert_many(docs)
        total += len(docs)
        logger.info("Joueurs FotMob %s (saison %s): %s (équipes rapprochées %s/%s)",
                    code, sname, len(docs), len(tmap), len(titles))

    await db.meta.update_one({"_id": "sync_players_fotmob"},
                             {"$set": {"_id": "sync_players_fotmob", "last_sync": now, "joueurs": total}},
                             upsert=True)
    return {"ok": True, "joueurs": total}
