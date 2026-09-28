"""Orchestration des synchronisations (planifiées ou au démarrage) : ingestion,
invalidation des caches d'analyse, puis règlement / prise des paris."""
import logging
from datetime import datetime, timezone

from analytics import invalidate_caches
from core import db
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
