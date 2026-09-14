"""Ingestion quotidienne depuis football-data.org vers MongoDB.

Récupère, par championnat : tous les matchs de la saison (historique + à venir)
et le classement. Upsert idempotent (aucun doublon). Ne récupère aucune donnée
individuelle de joueur (non fournie par la source gratuite).
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from football_client import FootballDataClient, get_token
from player_ingest import ingest_players
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
}


def configured_codes():
    raw = os.environ.get("COMPETITIONS", "PL,PD,SA,BL1,FL1,PPL,DED")
    return [c.strip().upper() for c in raw.split(",") if c.strip() in COMPETITION_META]


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
        for item in payload.get("matches", []):
            code = (item.get("competition") or {}).get("code")
            if code not in allowed:
                continue
            await db.matches.update_one({"match_id": item["id"]},
                                        {"$set": _match_doc(item, code, now)}, upsert=True)
            count += 1
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


async def run_ingest(db):
    token = get_token()
    if not token:
        logger.warning("FOOTBALL_DATA_TOKEN manquant — ingestion ignorée.")
        return {"ok": False, "raison": "token_manquant"}

    client = FootballDataClient(token)
    now = datetime.now(timezone.utc)
    stats = {"matchs": 0, "championnats": 0}
    try:
        for code in configured_codes():
            try:
                data = await client.competition_matches(code)
            except Exception as e:  # noqa: BLE001
                logger.error("Echec matchs %s: %s", code, e)
                continue
            for item in data.get("matches", []):
                ft = (item.get("score") or {}).get("fullTime") or {}
                udate = item.get("utcDate")
                doc = {
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
                await db.matches.update_one({"match_id": item["id"]}, {"$set": doc}, upsert=True)
                stats["matchs"] += 1

            try:
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

    return {"ok": True, "synced_at": now.isoformat(), **stats, "joueurs": pstats}
