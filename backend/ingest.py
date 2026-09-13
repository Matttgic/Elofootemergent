"""Ingestion quotidienne depuis football-data.org vers MongoDB.

Récupère, par championnat : tous les matchs de la saison (historique + à venir)
et le classement. Upsert idempotent (aucun doublon). Ne récupère aucune donnée
individuelle de joueur (non fournie par la source gratuite).
"""
import logging
import os
from datetime import datetime, timezone

from football_client import FootballDataClient, get_token
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
        logger.info("Ingestion terminée: %s", stats)
        return {"ok": True, "synced_at": now.isoformat(), **stats}
    finally:
        await client.close()
