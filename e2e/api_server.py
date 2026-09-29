"""API simulée pour les tests navigateur : le jeu de données des tests hors ligne
(backend/tests/test_api_offline.py) dans une base mongomock, sans réseau ni jeton.
Écoute sur 127.0.0.1:8765. Nécessite backend/requirements-dev.txt."""
import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
os.chdir(BACKEND)
os.environ.update(MONGO_URL="mongodb://e2e", DB_NAME="footpulse_e2e", FOOTBALL_DATA_TOKEN="",
                  SCHEDULER_ENABLED="false", COMPETITIONS="PL,CL", CORS_ORIGINS="*")
os.environ.pop("ODDS_API_KEY", None)

import mongomock_motor  # noqa: E402
import motor.motor_asyncio as motor_asyncio  # noqa: E402

motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

import server  # noqa: E402
import uvicorn  # noqa: E402
from routers import players as players_router  # noqa: E402
from routers.stats import settle_bets  # noqa: E402
from test_api_offline import dataset  # noqa: E402


async def _no_network(*args, **kwargs):
    return []


# forme récente des joueurs : aucun appel à Understat / FotMob pendant les tests
players_router.fetch_player_matches = _no_network
players_router.fetch_player_recent = _no_network

# logos servis par le site lui-même (pas de réseau pendant les tests)
LOGO = "http://127.0.0.1:8766/favicon.svg"


async def seed(db):
    matches, table, players, form, bets, history = dataset()
    for m in matches + history:
        for side in ("home_team", "away_team"):
            m[side]["crest"] = LOGO
    for row in table:
        row["team"]["crest"] = LOGO
    await db.matches.insert_many(matches)
    await db.matches_history.insert_many(history)
    await db.standings.insert_one({"competition_code": "PL", "table": table})
    await db.players.insert_many(players)
    await db.player_form.insert_one({"_id": "100", "updated_at": "2099-01-01T00:00:00+00:00", "data": form})
    await db.bets.insert_many(bets)
    await settle_bets()


if __name__ == "__main__":
    asyncio.run(seed(server.db))
    uvicorn.run(server.app, host="127.0.0.1", port=8765, log_level="warning")
