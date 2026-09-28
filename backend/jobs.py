"""Orchestration des synchronisations (planifiées ou au démarrage) : ingestion,
invalidation des caches d'analyse, puis règlement / prise des paris.

Utilisable aussi en ligne de commande, par exemple depuis un cron externe
(GitHub Actions) quand l'API tourne sur un hébergement qui se met en veille :
    python -m jobs light   # résultats récents (1 appel football-data)
    python -m jobs full    # saison, classements, joueurs, cotes
"""
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from analytics import invalidate_caches
from core import client, db
from ingest import run_ingest, run_light_ingest
from routers.stats import settle_bets, snapshot_bets

logger = logging.getLogger(__name__)

# État de synchronisation (évite les ingestions concurrentes manuel/planifié)
ingest_state = {"running": False, "started_at": None}


async def _guarded(factory):
    if ingest_state["running"]:
        logger.info("Ingestion déjà en cours — appel ignoré.")
        return {"ok": False, "raison": "deja_en_cours"}
    ingest_state["running"] = True
    ingest_state["started_at"] = datetime.now(timezone.utc).isoformat()
    try:
        return await factory()
    finally:
        ingest_state["running"] = False
        invalidate_caches()   # les analyses reflètent immédiatement les nouvelles données


async def run_full_guarded():
    res = await _guarded(lambda: run_ingest(db))
    try:
        await settle_bets()
        await snapshot_bets()
    except Exception as e:  # noqa: BLE001
        logger.error("Simulation paris (full) échec: %s", e)
    return res


async def run_light_guarded():
    res = await _guarded(lambda: run_light_ingest(db))
    try:
        await settle_bets()
    except Exception as e:  # noqa: BLE001
        logger.error("Règlement paris (light) échec: %s", e)
    return res


async def ensure_indexes():
    await db.matches.create_index("match_id", unique=True)
    await db.matches.create_index([("competition_code", 1), ("match_date", 1)])
    await db.standings.create_index("competition_code", unique=True)
    await db.players.create_index([("competition_code", 1), ("team_id", 1)])
    await db.players.create_index("player_id")


async def main(mode):
    await ensure_indexes()
    res = await (run_full_guarded() if mode == "full" else run_light_guarded())
    print(json.dumps(res, ensure_ascii=False, default=str))
    return 0 if (res or {}).get("ok") else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("light", "full"):
        sys.exit("usage : python -m jobs light|full")
    try:
        code = asyncio.run(main(sys.argv[1]))
    finally:
        client.close()
    sys.exit(code)
