"""Client for football-data.org API v4 (free tier).

Free tier: 10 requests/minute, authenticated via X-Auth-Token header.
Provides fixtures/results and league standings. No player-level data.
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

BASE = "https://api.football-data.org/v4"


class FootballDataClient:
    def __init__(self, token: str):
        self.token = token
        self.http = httpx.AsyncClient(
            base_url=BASE,
            headers={"X-Auth-Token": token},
            timeout=30,
        )
        self._last_request = 0.0

    async def close(self):
        await self.http.aclose()

    async def _get(self, path: str, params: dict | None = None):
        # 6.5s spacing keeps us safely under 10 req/min on the free tier.
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self._last_request
        if elapsed < 6.5:
            await asyncio.sleep(6.5 - elapsed)
        for attempt in range(4):
            self._last_request = loop.time()
            resp = await self.http.get(path, params=params)
            if resp.status_code == 429:
                reset = resp.headers.get("X-RequestCounter-Reset")
                delay = int(reset) + 1 if reset and reset.isdigit() else 60
                logger.warning("Rate limited, waiting %ss", min(delay, 120))
                await asyncio.sleep(min(delay, 120))
                continue
            if resp.status_code in (408, 500, 502, 503, 504):
                if attempt == 3:
                    resp.raise_for_status()
                await asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"football-data request failed: {path}")

    async def competition_matches(self, code: str, season: int | None = None):
        """Tous les matchs d'une saison (en cours par défaut ; `season` = année de début)."""
        return await self._get(f"/competitions/{code}/matches", {"season": season} if season else None)

    async def matches_window(self, date_from: str, date_to: str):
        """Tous les matchs (tous championnats) sur une fenêtre de dates — 1 appel."""
        return await self._get("/matches", {"dateFrom": date_from, "dateTo": date_to})

    async def standings(self, code: str):
        return await self._get(f"/competitions/{code}/standings")


def get_token() -> str:
    return (os.environ.get("FOOTBALL_DATA_TOKEN") or "").strip()
