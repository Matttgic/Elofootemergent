"""Client de cotes 1N2 (The Odds API, plan gratuit). Aucune donnée inventée :
on ne lit que les vraies cotes des matchs à venir. Quota surveillé via en-têtes.
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

BASE = "https://api.the-odds-api.com/v4"

# code football-data -> clé sport The Odds API
ODDS_SPORT = {
    "PL": "soccer_epl",
    "PD": "soccer_spain_la_liga",
    "SA": "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "PPL": "soccer_portugal_primeira_liga",
    "DED": "soccer_netherlands_eredivisie",
    "CL": "soccer_uefa_champs_league",
}

# préférence bookmaker : France d'abord, sinon bet365, puis références solides
BOOK_PREF = ["betclic_fr", "winamax_fr", "unibet_fr", "pmu_fr", "parionssport_fr",
             "bet365", "pinnacle", "williamhill", "betfair_ex_eu"]


def _pick_book(bookmakers):
    by_key = {b["key"]: b for b in bookmakers}
    for k in BOOK_PREF:
        if k in by_key:
            return by_key[k]
    return bookmakers[0] if bookmakers else None


async def fetch_odds(sport_key):
    """Retourne les cotes 1N2 (une par match, du bookmaker préféré) pour un championnat."""
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        return []
    params = {"apiKey": api_key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(f"{BASE}/sports/{sport_key}/odds", params=params)
    if r.status_code == 429:
        logger.warning("The Odds API : quota/limite atteinte (%s)", sport_key)
        return []
    r.raise_for_status()
    logger.info("The Odds API %s : %s requêtes restantes ce mois",
                sport_key, r.headers.get("x-requests-remaining"))
    out = []
    for fx in r.json():
        book = _pick_book(fx.get("bookmakers") or [])
        if not book:
            continue
        h2h = next((m for m in book.get("markets", []) if m.get("key") == "h2h"), None)
        if not h2h:
            continue
        prices = {o["name"]: o["price"] for o in h2h.get("outcomes", [])}
        home, away = fx.get("home_team"), fx.get("away_team")
        out.append({
            "home_team": home, "away_team": away,
            "commence_time": fx.get("commence_time"),
            "home_odds": prices.get(home),
            "away_odds": prices.get(away),
            "draw_odds": prices.get("Draw"),
            "bookmaker": book.get("title") or book.get("key"),
        })
    return out
