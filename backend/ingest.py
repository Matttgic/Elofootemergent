"""Ingestion quotidienne depuis football-data.org vers MongoDB.

Récupère, par championnat : tous les matchs de la saison (historique + à venir)
et le classement ; une seule fois, les deux saisons précédentes (Elo). Upsert
idempotent (aucun doublon). Les statistiques de joueurs viennent d'autres
sources (player_ingest).
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from pymongo import UpdateOne

from football_client import FootballDataClient, get_token
from player_ingest import ingest_players, ingest_fotmob_players
from scoring import paris_date

logger = logging.getLogger(__name__)

# Championnats européens disponibles sur l'offre gratuite de football-data.org.
# L'architecture permet d'en ajouter simplement via la variable COMPETITIONS.
COMPETITION_META = {
    "PL":  {"nom": "Premier League", "pays": "Angleterre"},
    "PD":  {"nom": "La Liga", "pays": "Espagne"},
    "SA":  {"nom": "Serie A", "pays": "Italie"},
    "BL1": {"nom": "Bundesliga", "pays": "Allemagne"},
    "FL1": {"nom": "Ligue 1", "pays": "France"},
    "PPL": {"nom": "Primeira Liga", "pays": "Portugal"},
    "DED": {"nom": "Eredivisie", "pays": "Pays-Bas"},
    "ELC": {"nom": "Championship", "pays": "Angleterre"},
    "BSA": {"nom": "Série A (Brésil)", "pays": "Brésil"},
    "CL":  {"nom": "Ligue des Champions", "pays": "Europe", "cup": True},
    "EC":  {"nom": "Championnat d'Europe", "pays": "Europe", "cup": True},
    "WC":  {"nom": "Coupe du Monde", "pays": "Monde", "cup": True},
}


def is_cup(code):
    return bool(COMPETITION_META.get(code, {}).get("cup"))


def configured_codes():
    """Compétitions synchronisées : variable COMPETITIONS (codes séparés par des
    virgules), sinon toutes celles de l'offre gratuite football-data.org."""
    raw = os.environ.get("COMPETITIONS") or ",".join(COMPETITION_META)
    return [c.strip().upper() for c in raw.split(",") if c.strip().upper() in COMPETITION_META]


# Saisons précédentes chargées une seule fois (résultats figés) pour l'Elo et les
# confrontations directes. Refus éventuel de l'offre gratuite : nouvel essai après 7 jours.
HISTORY_SEASONS = 2
HISTORY_RETRY = timedelta(days=7)


def _match_doc(item, code, now):
    udate = item.get("utcDate")
    return {
        "match_id": item["id"],
        "competition_code": code,
        "utc_date": udate,
        "match_date": paris_date(udate) if udate else None,
        "status": item.get("status"),
        "matchday": item.get("matchday"),
        "home_team": item.get("homeTeam"),
        "away_team": item.get("awayTeam"),
        "score": item.get("score"),
        "last_synced_at": now.isoformat(),
    }


async def run_light_ingest(db):
    """Rafraîchissement léger et économe : 1 SEUL appel football-data (/matches sur
    une fenêtre de dates, tous championnats) pour mettre à jour les résultats récents
    et recalculer les notes. N'actualise ni les classements ni les joueurs."""
    token = get_token()
    if not token:
        return {"ok": False, "raison": "token_manquant"}
    client = FootballDataClient(token)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=2)).date().isoformat()
    end = (now + timedelta(days=3)).date().isoformat()  # dateTo exclusif côté API
    allowed = set(configured_codes())
    count = 0
    try:
        payload = await client.matches_window(start, end)
        docs = [_match_doc(item, (item.get("competition") or {}).get("code"), now)
                for item in payload.get("matches", [])
                if (item.get("competition") or {}).get("code") in allowed]
        count = await _upsert_matches(db.matches, docs)
        await db.meta.update_one(
            {"_id": "sync"},
            {"$set": {"_id": "sync", "last_sync": now.isoformat(), "mode": "leger", "matchs_maj": count}},
            upsert=True,
        )
        logger.info("Rafraîchissement léger: %s matchs mis à jour (1 appel API)", count)
        return {"ok": True, "mode": "leger", "matchs_maj": count, "appels_api": 1}
    except Exception as e:  # noqa: BLE001
        logger.error("Rafraîchissement léger échoué: %s", e)
        return {"ok": False, "raison": str(e)}
    finally:
        await client.close()


async def _upsert_matches(collection, docs):
    """Upsert groupé (un aller-retour pour tout le lot au lieu d'un par match :
    la synchro tourne loin de la base). Retourne le nombre de matchs écrits."""
    if docs:
        await collection.bulk_write([UpdateOne({"match_id": d["match_id"]}, {"$set": d}, upsert=True)
                                     for d in docs], ordered=False)
    return len(docs)


def _season_year(payload):
    """Année de début de la saison renvoyée par football-data (ex. 2026 pour 2026-27)."""
    raw = (payload.get("filters") or {}).get("season")
    if raw and str(raw).isdigit():
        return int(raw)
    for item in payload.get("matches", []):
        start = (item.get("season") or {}).get("startDate")
        if start:
            return int(start[:4])
    return None


async def ingest_history(db, client, code, current_season, now=None):
    """Charge dans `matches_history` les HISTORY_SEASONS saisons précédant la saison en
    cours (une seule fois : elles ne changent plus). Sélections nationales ignorées."""
    if not current_season or code in ("EC", "WC"):
        return 0
    now = now or datetime.now(timezone.utc)
    done = ((await db.meta.find_one({"_id": "history"})) or {}).get("saisons", {})
    loaded = 0
    for season in range(current_season - 1, current_season - 1 - HISTORY_SEASONS, -1):
        key = f"{code}-{season}"
        state = done.get(key) or {}
        if state.get("statut") == "ok":
            continue
        if state.get("at") and now - datetime.fromisoformat(state["at"]) < HISTORY_RETRY:
            continue
        try:
            payload = await client.competition_matches(code, season)
        except httpx.HTTPStatusError as e:
            code_http = e.response.status_code
            logger.warning("Historique %s refusé (HTTP %s)", key, code_http)
            await db.meta.update_one({"_id": "history"}, {"$set": {f"saisons.{key}": {
                "statut": "refuse", "http": code_http, "at": now.isoformat()}}}, upsert=True)
            continue
        docs = [{**_match_doc(item, code, now), "season": season} for item in payload.get("matches", [])]
        n = await _upsert_matches(db.matches_history, docs)
        await db.meta.update_one({"_id": "history"}, {"$set": {f"saisons.{key}": {
            "statut": "ok", "matchs": n, "at": now.isoformat()}}}, upsert=True)
        loaded += n
    return loaded


async def run_ingest(db):
    token = get_token()
    if not token:
        logger.warning("FOOTBALL_DATA_TOKEN manquant — ingestion ignorée.")
        return {"ok": False, "raison": "token_manquant"}

    client = FootballDataClient(token)
    now = datetime.now(timezone.utc)
    stats = {"matchs": 0, "championnats": 0, "historique": 0}
    try:
        for code in configured_codes():
            try:
                data = await client.competition_matches(code)
            except Exception as e:  # noqa: BLE001
                logger.error("Echec matchs %s: %s", code, e)
                continue
            stats["matchs"] += await _upsert_matches(
                db.matches, [_match_doc(item, code, now) for item in data.get("matches", [])])
            try:
                stats["historique"] += await ingest_history(db, client, code, _season_year(data), now)
            except Exception as e:  # noqa: BLE001
                logger.error("Echec historique %s: %s", code, e)

            try:
                if is_cup(code):
                    stats["championnats"] += 1
                    continue  # pas de classement pour les coupes
                sd = await client.standings(code)
                total = next((s for s in sd.get("standings", []) if s.get("type") == "TOTAL"), None)
                await db.standings.update_one(
                    {"competition_code": code},
                    {"$set": {
                        "competition_code": code,
                        "table": (total or {}).get("table", []),
                        "season": sd.get("season"),
                        "last_synced_at": now.isoformat(),
                    }},
                    upsert=True,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("Echec classement %s: %s", code, e)
            stats["championnats"] += 1

        await db.meta.update_one(
            {"_id": "sync"},
            {"$set": {"_id": "sync", "last_sync": now.isoformat(), **stats}},
            upsert=True,
        )
        logger.info("Ingestion équipes terminée: %s", stats)
    finally:
        await client.close()

    try:
        pstats = await ingest_players(db)
        logger.info("Ingestion joueurs terminée: %s", pstats)
    except Exception as e:  # noqa: BLE001
        logger.error("Ingestion joueurs échouée: %s", e)
        pstats = {"ok": False}

    try:
        fmstats = await ingest_fotmob_players(db)
        logger.info("Ingestion joueurs FotMob terminée: %s", fmstats)
    except Exception as e:  # noqa: BLE001
        logger.error("Ingestion joueurs FotMob échouée: %s", e)
        fmstats = {"ok": False}

    try:
        from xg_ingest import ingest_xg   # import local : xg_ingest dépend de ce module
        xgstats = await ingest_xg(db, now)
        logger.info("xG Understat : %s", xgstats)
    except Exception as e:  # noqa: BLE001
        logger.error("xG Understat échec : %s", e)
        xgstats = {"ok": False}

    try:
        from cotes_ingest import ingest_cotes   # import local : cotes_ingest dépend de ce module
        cotestats = await ingest_cotes(db, now)
        logger.info("Cotes football-data.co.uk : %s", cotestats)
    except Exception as e:  # noqa: BLE001
        logger.error("Cotes football-data.co.uk échec : %s", e)
        cotestats = {"ok": False}

    return {"ok": True, "synced_at": now.isoformat(), **stats,
            "joueurs": pstats, "joueurs_fotmob": fmstats, "xg": xgstats, "cotes": cotestats}
