"""Client Understat (source gratuite de statistiques individuelles + xG/xA).

Understat expose ses données via un endpoint AJAX JSON. Aucune donnée n'est
inventée : on lit uniquement ce que renvoie la source. Couverture : 5 grands
championnats (Premier League, La Liga, Bundesliga, Serie A, Ligue 1).
"""
import logging
import httpx

logger = logging.getLogger(__name__)

BASE = "https://understat.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# code football-data.org -> clé de championnat Understat
UNDERSTAT_LEAGUES = {
    "PL": "EPL",
    "PD": "La_liga",
    "BL1": "Bundesliga",
    "SA": "Serie_A",
    "FL1": "Ligue_1",
}


async def fetch_players(league_key: str, season: int):
    url = f"{BASE}/main/getPlayersStats/"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, headers={**HEADERS, "Referer": f"{BASE}/league/{league_key}/{season}"},
                         data={"league": league_key, "season": str(season)})
        r.raise_for_status()
        data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"Understat: réponse invalide pour {league_key}/{season}")
    return data.get("players", [])
