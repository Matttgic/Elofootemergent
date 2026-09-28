"""Point d'entrée FastAPI (uvicorn server:app) : application, CORS, planification
des synchronisations et démarrage. Les routes sont dans routers/."""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from core import client, db
from football_client import get_token
from jobs import run_full_guarded, run_light_guarded
from routers import matches, players, stats

logger = logging.getLogger(__name__)

app = FastAPI(title="FootPulse Analytics API")
for module in (matches, players, stats):
    app.include_router(module.router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _startup_ingest():
    await db.matches.create_index("match_id", unique=True)
    await db.matches.create_index([("competition_code", 1), ("match_date", 1)])
    await db.standings.create_index("competition_code", unique=True)
    await db.players.create_index([("competition_code", 1), ("team_id", 1)])
    await db.players.create_index("player_id")
    if not get_token():
        return
    nb = await db.matches.count_documents({})
    stale = True
    sync = await db.meta.find_one({"_id": "sync"})
    if sync and sync.get("last_sync"):
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(sync["last_sync"])
            stale = age > timedelta(hours=3)
        except Exception:  # noqa: BLE001
            stale = True
    if nb == 0:
        logger.info("Base vide — analyse complète en arrière-plan.")
        asyncio.create_task(run_full_guarded())
    elif stale:
        logger.info("Données périmées — rafraîchissement léger de rattrapage.")
        asyncio.create_task(run_light_guarded())


@app.on_event("startup")
async def on_startup():
    await _startup_ingest()
    # Rafraîchissement léger fréquent (1 appel API) pour les résultats + notes
    scheduler.add_job(run_light_guarded, "cron", minute=5,
                      id="light", replace_existing=True, max_instances=1, coalesce=True)
    # Analyse complète 1×/jour (saison + classements + joueurs)
    scheduler.add_job(run_full_guarded, "cron", hour=4, minute=30,
                      id="full", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)
    client.close()
