"""Cotes 1N2 des matchs, rattachées aux matchs football-data pour la fiche match
(« Selon les cotes historiques »). Source : football-data.co.uk, sans clé :
  - fixtures.csv : matchs à venir, cotes moyennes des bookmakers avant le match
    (publié en fin de semaine pour le week-end et en début de semaine pour le milieu) ;
  - fichier de la saison : matchs joués, cotes moyennes à la clôture.
Le Brésil est dans les fichiers « new » (new/BRA.csv, new_league_fixtures.csv).

Les noms d'équipes football-data.co.uk sont gardés avec les cotes : ce sont ceux de
l'historique des cotes (cotes_historiques). Le rapprochement avec les matchs
football-data est celui des xG (xg_ingest.pair_fixtures) : correspondance des noms
apprise sur les résultats (saison en cours et précédente), puis équipes et date ± 1 jour.
"""
import csv
import io
import logging
from datetime import datetime, timezone

import httpx
from pymongo import UpdateOne

from ingest import configured_codes
from xg_ingest import pair_fixtures

logger = logging.getLogger(__name__)

BASE = "https://www.football-data.co.uk"
DIVISIONS = {"PL": "E0", "ELC": "E1", "PD": "SP1", "SA": "I1", "BL1": "D1", "FL1": "F1", "PPL": "P1", "DED": "N1"}
NEW_LEAGUES = {"BSA": ("BRA", "Brazil", "Serie A")}      # code : (fichier, pays, championnat)
SOURCE = "football-data.co.uk (moyenne des bookmakers)"
OVERROUND = (0.95, 1.2)       # somme des 1/cote acceptée (marge de -5 % à +20 %)

# colonnes de cotes, par ordre de préférence : moyenne puis Bet365, clôture puis avant-match
CLOTURE = (("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA"))
AVANT = (("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A"))


async def _fetch(client, path):
    """Texte d'un fichier football-data.co.uk ('' s'il n'existe pas encore)."""
    r = await client.get(f"{BASE}/{path}")
    if r.status_code == 404:
        return ""
    r.raise_for_status()
    return r.content.decode("utf-8-sig", errors="replace")


def _rows(text):
    if not text.strip():
        return []
    first = text.split("\n", 1)[0]
    return list(csv.DictReader(io.StringIO(text), delimiter="\t" if "\t" in first else ","))


def _odds(row, groups):
    for cols in groups:
        try:
            o = [float(row[c]) for c in cols]
        except (KeyError, TypeError, ValueError):
            continue
        if all(x > 1 for x in o) and OVERROUND[0] <= sum(1 / x for x in o) <= OVERROUND[1]:
            return o
    return None


def _utc(date, time):
    dd, mm, yy = date.strip().split("/")
    yy = "20" + yy if len(yy) == 2 else yy
    return f"{yy}-{mm}-{dd}T{(time or '12:00').strip()[:5]}:00Z"


def parse_fixtures(text, home="HomeTeam", away="AwayTeam", hg="FTHG", ag="FTAG", keep=lambda r: True):
    """Lignes d'un fichier football-data.co.uk -> matchs {home, away, utc, score, odds, type} :
    cotes à la clôture pour un match joué, avant le match sinon."""
    out = []
    for r in _rows(text):
        if not keep(r) or not r.get(home) or not r.get(away) or not r.get("Date"):
            continue
        try:
            score = (int(r[hg]), int(r[ag]))
        except (KeyError, TypeError, ValueError):
            score = None
        odds, kind = (_odds(r, CLOTURE), "cloture") if score else (None, None)
        if not odds:
            odds, kind = _odds(r, AVANT), "avant-match"
        try:
            utc = _utc(r["Date"], r.get("Time"))
        except ValueError:
            continue
        out.append({"home": r[home].strip(), "away": r[away].strip(), "utc": utc, "score": score,
                    "odds": odds, "type": kind})
    return out


def _season_code(now):
    y = now.year if now.month >= 7 else now.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}", f"{(y - 1) % 100:02d}{y % 100:02d}"


def odds_ops(fixtures, fd_matches, current_ids, now):
    """Écritures `cotes_ref` des matchs de la saison en cours rapprochés (les matchs
    passés servent seulement à apprendre les noms). Retourne (ops, non rapprochés)."""
    pairs, _ = pair_fixtures(fixtures, fd_matches)
    ops, paired = {}, set()
    for fx, mid in pairs:
        paired.add(id(fx))
        if mid not in current_ids or not fx["odds"]:
            continue
        # clôture prioritaire sur avant-match si les deux fichiers ont le match
        if mid in ops and ops[mid][1] == "cloture":
            continue
        ops[mid] = (UpdateOne({"match_id": mid}, {"$set": {"cotes_ref": {
            "domicile": fx["odds"][0], "nul": fx["odds"][1], "exterieur": fx["odds"][2], "type": fx["type"],
            "source": SOURCE, "equipe_domicile": fx["home"], "equipe_exterieur": fx["away"],
            "at": now.isoformat()}}}), fx["type"])
    missed = sum(1 for fx in fixtures if fx["odds"] and id(fx) not in paired and fx["utc"] >= now.isoformat()[:10])
    return [op for op, _ in ops.values()], missed


PROJ = {"_id": 0, "match_id": 1, "utc_date": 1, "home_team": 1, "away_team": 1, "score.fullTime": 1}


async def ingest_cotes(db, now=None, client=None):
    """Rattache les cotes football-data.co.uk aux matchs de la saison en cours."""
    now = now or datetime.now(timezone.utc)
    cur, prev = _season_code(now)
    stats = {"rattaches": 0, "a_venir_non_rattaches": 0, "championnats": 0}
    own = client is None
    client = client or httpx.AsyncClient(timeout=60, follow_redirects=True)
    try:
        codes = [c for c in configured_codes() if c in DIVISIONS or c in NEW_LEAGUES]
        if not codes:
            return stats
        upcoming = await _fetch(client, "fixtures.csv") if any(c in DIVISIONS for c in codes) else ""
        new_upcoming = await _fetch(client, "new_league_fixtures.csv") if any(c in NEW_LEAGUES for c in codes) else ""
        for code in codes:
            try:
                if code in DIVISIONS:
                    div = DIVISIONS[code]
                    fixtures = parse_fixtures(await _fetch(client, f"mmz4281/{prev}/{div}.csv"))
                    fixtures += parse_fixtures(await _fetch(client, f"mmz4281/{cur}/{div}.csv"))
                    fixtures += parse_fixtures(upcoming, keep=lambda r, d=div: r.get("Div") == d)
                else:
                    name, country, league = NEW_LEAGUES[code]
                    keep = (lambda r, c=country, lg=league: r.get("Country") == c and r.get("League") == lg)
                    fixtures = parse_fixtures(await _fetch(client, f"new/{name}.csv"), "Home", "Away", "HG", "AG")
                    fixtures = [f for f in fixtures if f["utc"][:4] >= str(now.year - 1)]
                    fixtures += parse_fixtures(new_upcoming, "Home", "Away", "HG", "AG", keep=keep)
            except Exception as e:  # noqa: BLE001
                logger.error("Cotes football-data.co.uk %s échec : %s", code, e)
                continue
            current = await db.matches.find({"competition_code": code}, PROJ).to_list(2000)
            history = await db.matches_history.find({"competition_code": code, "status": "FINISHED"}, PROJ).to_list(2000)
            ops, missed = odds_ops(fixtures, current + history, {m["match_id"] for m in current}, now)
            if ops:
                await db.matches.bulk_write(ops, ordered=False)
            stats["rattaches"] += len(ops)
            stats["a_venir_non_rattaches"] += missed
            stats["championnats"] += 1
            logger.info("Cotes %s : %s matchs rattachés, %s à venir non rattachés", code, len(ops), missed)
    finally:
        if own:
            await client.aclose()
    return stats
