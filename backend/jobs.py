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
from datetime import datetime, timedelta, timezone

from analytics import invalidate_caches
from core import client, db
from football_client import get_token
from ingest import run_ingest, run_light_ingest
from routers.stats import settle_bets, snapshot_bets

logger = logging.getLogger(__name__)

# État de synchronisation (évite les ingestions concurrentes manuel/planifié)
ingest_state = {"running": False, "started_at": None}

# Rattrapage si la synchro externe (cron GitHub, parfois en retard) n'est pas passée
CATCH_UP_AFTER = timedelta(hours=2)
CATCH_UP_RETRY = timedelta(minutes=30)
_catch_up = {"last_attempt": None}
_background = set()   # références des tâches lancées (évite leur ramasse-miettes)


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


async def catch_up_if_stale():
    """Filet de sécurité : si la dernière synchro date de plus de CATCH_UP_AFTER,
    lance un rafraîchissement léger (1 appel API) en arrière-plan. Au plus une
    tentative par CATCH_UP_RETRY et par processus. Retourne True si lancé."""
    now = datetime.now(timezone.utc)
    last = _catch_up["last_attempt"]
    if not get_token() or ingest_state["running"] or (last and now - last < CATCH_UP_RETRY):
        return False
    sync = await db.meta.find_one({"_id": "sync"}, {"last_sync": 1})
    try:
        if now - datetime.fromisoformat(sync["last_sync"]) < CATCH_UP_AFTER:
            return False
    except (TypeError, KeyError, ValueError):
        pass   # jamais synchronisé ou date illisible : on rattrape
    _catch_up["last_attempt"] = now
    logger.info("Données périmées — rafraîchissement léger de rattrapage.")
    task = asyncio.create_task(run_light_guarded())
    _background.add(task)
    task.add_done_callback(_background.discard)
    return True


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
