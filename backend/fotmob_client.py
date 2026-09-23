"""Client FotMob (source gratuite, sans clé) pour les statistiques individuelles
des championnats non couverts par Understat : Primeira Liga (Portugal) et
Eredivisie (Pays-Bas).

FotMob expose des fichiers JSON publics par statistique et par saison :
    https://data.fotmob.com/stats/{leagueId}/season/{seasonId}/{stat}.json
et la liste des saisons via :
    https://www.fotmob.com/api/data/leagueseasondeepstats?id={leagueId}&type=players&stat=goals

Aucune donnée n'est inventée : on lit uniquement ce que renvoie la source.
"""
import logging
import httpx

logger = logging.getLogger(__name__)

# code football-data.org -> identifiant de ligue FotMob
FOTMOB_LEAGUES = {"PPL": 61, "DED": 57}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

DEEP = "https://www.fotmob.com/api/data/leagueseasondeepstats"
DATA = "https://data.fotmob.com/stats/{lid}/season/{sid}/{stat}.json"
PLAYER_DATA = "https://www.fotmob.com/api/data/playerData"

# Statistiques FotMob nécessaires (nom FotMob -> clé interne). total_scoring_att
# est fourni PAR 90 MIN (les autres sont des totaux de saison).
STAT_TOTALS = {
    "goals": "goals",
    "goal_assist": "assists",
    "expected_goals": "xG",
    "expected_assists": "xA",
    "total_att_assist": "key_passes",
    "yellow_card": "yellow",
    "red_card": "red",
}
STAT_PER90 = {"total_scoring_att": "shots"}


async def _stat_list(client: httpx.AsyncClient, lid: int, sid: int, stat: str):
    url = DATA.format(lid=lid, sid=sid, stat=stat)
    r = await client.get(url)
    r.raise_for_status()
    data = r.json()
    tl = data.get("TopLists") or []
    return tl[0].get("StatList", []) if tl else []


async def _seasons(client: httpx.AsyncClient, lid: int):
    r = await client.get(DEEP, params={"id": lid, "type": "players", "stat": "goals"})
    r.raise_for_status()
    return r.json().get("seasons", [])


async def resolve_season(client: httpx.AsyncClient, lid: int, target_name: str | None = None):
    """Choisit la saison FotMob alignée sur la saison en cours de football-data.

    Si `target_name` (ex : "2026/2027") est fourni et présent chez FotMob avec des
    données, on l'utilise. Sinon, on prend — parmi les 2 saisons les plus récentes —
    celle qui contient le plus de joueurs (la nouvelle saison étant vide en intersaison).
    """
    seasons = await _seasons(client, lid)
    if target_name:
        for s in seasons:
            if s.get("name") == target_name:
                try:
                    if len(await _stat_list(client, lid, s["id"], "goals")) > 0:
                        return s["id"], s.get("name")
                except Exception:  # noqa: BLE001
                    pass
                break
    best_id, best_name, best_n = None, None, -1
    for s in seasons[:2]:
        try:
            n = len(await _stat_list(client, lid, s["id"], "goals"))
        except Exception:  # noqa: BLE001
            n = 0
        if n > best_n:
            best_id, best_name, best_n = s["id"], s.get("name"), n
    return best_id, best_name


async def fetch_league_players(lid: int, target_name: str | None = None):
    """Retourne (season_id, season_name, liste de joueurs fusionnés) pour une ligue."""
    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        sid, sname = await resolve_season(client, lid, target_name)
        if sid is None:
            raise RuntimeError(f"FotMob: aucune saison exploitable pour la ligue {lid}")

        players = {}

        def _ensure(entry):
            pid = entry.get("ParticiantId")
            if pid is None:
                return None
            p = players.get(pid)
            if p is None:
                p = players[pid] = {
                    "id": pid,
                    "nom": entry.get("ParticipantName"),
                    "team_title": entry.get("TeamName"),
                    "team_fotmob_id": entry.get("TeamId"),
                    "positions": entry.get("Positions") or [],
                    "minutes": entry.get("MinutesPlayed") or 0,
                    "games": entry.get("MatchesPlayed") or 0,
                    "goals": 0, "assists": 0, "shots": 0, "key_passes": 0,
                    "xG": 0.0, "xA": 0.0, "yellow": 0, "red": 0,
                }
            # minutes/matchs = valeur maximale rencontrée (la plus complète)
            if (entry.get("MinutesPlayed") or 0) > p["minutes"]:
                p["minutes"] = entry.get("MinutesPlayed") or 0
                p["games"] = entry.get("MatchesPlayed") or p["games"]
            return p

        # Base : minutes jouées (contient l'ensemble des joueurs ayant joué)
        for e in await _stat_list(client, lid, sid, "mins_played"):
            _ensure(e)

        for stat, key in STAT_TOTALS.items():
            try:
                for e in await _stat_list(client, lid, sid, stat):
                    p = _ensure(e)
                    if p is not None:
                        p[key] = e.get("StatValue") or 0
            except Exception as ex:  # noqa: BLE001
                logger.warning("FotMob %s/%s stat %s échec: %s", lid, sid, stat, ex)

        for stat, key in STAT_PER90.items():  # valeur par 90 -> total
            try:
                for e in await _stat_list(client, lid, sid, stat):
                    p = _ensure(e)
                    if p is not None:
                        per90 = e.get("StatValue") or 0
                        p[key] = round(per90 * (p["minutes"] / 90.0)) if p["minutes"] else 0
            except Exception as ex:  # noqa: BLE001
                logger.warning("FotMob %s/%s stat %s échec: %s", lid, sid, stat, ex)

        return sid, sname, list(players.values())


async def fetch_player_recent(fotmob_id):
    """Derniers matchs joués d'un joueur (toutes compétitions), sans clé API."""
    async with httpx.AsyncClient(timeout=25, headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(PLAYER_DATA, params={"id": fotmob_id})
        r.raise_for_status()
        return r.json().get("recentMatches") or []



def fotmob_poste(positions):
    """Traduit les codes de position FotMob en libellé F/M/D/GK (approximation)."""
    if not positions:
        return "M"
    c = positions[0]
    if c < 30:
        return "GK"
    if c < 60:
        return "D"
    if c < 100:
        return "M"
    return "F"
