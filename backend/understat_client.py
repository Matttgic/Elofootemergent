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


async def fetch_league_matches(league_key: str, season: int):
    """Matchs joués d'une saison avec leurs xG (1 appel par championnat et par saison).
    Chaque élément : {"datetime", "h": {"title"}, "a": {"title"}, "goals", "xG"}."""
    url = f"{BASE}/getLeagueData/{league_key}/{season}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url, headers={**HEADERS, "Referer": f"{BASE}/league/{league_key}/{season}"})
        r.raise_for_status()
        data = r.json()
    return [d for d in data.get("dates", []) if d.get("isResult") and d.get("xG")]


async def fetch_player_matches(player_id: str):
    """Journal match par match d'un joueur (toutes saisons, du plus récent au plus ancien)."""
    url = f"{BASE}/main/getPlayerMatches/{player_id}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, headers={**HEADERS, "Referer": f"{BASE}/player/{player_id}"}, data={})
        r.raise_for_status()
        data = r.json()
    resp = data.get("response", data)
    return resp.get("matches", []) if isinstance(resp, dict) else []
