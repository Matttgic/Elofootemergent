"""Tests de l'API complète sans réseau ni MongoDB réel (base simulée mongomock).

Chaque endpoint est appelé via le TestClient FastAPI sur un jeu de données
généré (Premier League + Ligue des champions). Aucun appel externe : la forme
récente des joueurs est pré-remplie en cache et les clés d'API sont absentes.
Nécessite `mongomock-motor` (voir requirements-dev.txt) ; ignoré sinon.
"""
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NAMES = ["Arsenal FC", "Chelsea FC", "Liverpool FC", "Manchester City FC", "Manchester United FC",
         "Tottenham Hotspur FC", "Newcastle United FC", "Aston Villa FC", "Everton FC", "Fulham FC",
         "Brentford FC", "Burnley FC", "Leeds United FC", "Sunderland AFC", "West Ham United FC",
         "Crystal Palace FC", "Wolverhampton Wanderers FC", "Nottingham Forest FC",
         "Brighton & Hove Albion FC", "AFC Bournemouth"]
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def team(i):
    name = NAMES[i - 1]
    return {"id": i, "name": name, "shortName": name.replace(" FC", ""), "tla": "T%02d" % i,
            "crest": f"https://crests.example/{i}.png"}


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def dataset():
    """Saison PL de 8 journées jouées + 1 à venir, quelques matchs de CL, joueurs et paris."""
    rng = random.Random(7)
    strength = {i: rng.uniform(0.6, 2.2) for i in range(1, 21)}
    matches, mid = [], 0
    for r in range(9):
        ids = list(range(1, 21))
        rng.shuffle(ids)
        kick = NOW.replace(hour=15) - timedelta(days=7 * (8 - r)) + timedelta(days=2)
        for i in range(0, 20, 2):
            mid += 1
            h, a = ids[i], ids[i + 1]
            played = kick < NOW
            matches.append({
                "match_id": mid, "competition_code": "PL", "utc_date": iso(kick),
                "match_date": kick.date().isoformat(), "matchday": r + 1,
                "status": "FINISHED" if played else "TIMED",
                "home_team": team(h), "away_team": team(a),
                "score": {"fullTime": {"home": min(6, int(rng.expovariate(1 / strength[h]))) if played else None,
                                       "away": min(6, int(rng.expovariate(1 / strength[a]))) if played else None}},
            })
    for k, (h, a, gh, ga) in enumerate([(1, 4, 2, 1), (4, 3, 0, 0), (3, 1, 1, 2)]):
        kick = NOW - timedelta(days=20 - 7 * k)
        matches.append({"match_id": 1000 + k, "competition_code": "CL", "utc_date": iso(kick),
                        "match_date": kick.date().isoformat(), "matchday": k + 1, "status": "FINISHED",
                        "home_team": team(h), "away_team": team(a),
                        "score": {"fullTime": {"home": gh, "away": ga}}})
    table = [{"position": p, "team": team(t), "playedGames": 8, "won": 0, "draw": 0, "lost": 0,
              "points": 30 - p, "goalsFor": 0, "goalsAgainst": 0, "goalDifference": 0}
             for p, t in enumerate(sorted(strength, key=lambda t: -strength[t]), 1)]
    players = [{"player_id": str(100 + i), "competition_code": "PL", "season": 2026,
                "nom": f"Joueur {i}", "position": ["F", "M", "D", "GK"][i % 4],
                "team_title": team(1 + i % 20)["shortName"], "team_id": 1 + i % 20,
                "games": 8, "minutes": 200 + 80 * i, "goals": i % 7, "assists": i % 5, "shots": 3 * (i % 9),
                "key_passes": 2 * (i % 6), "xG": 0.6 * (i % 7), "xA": 0.4 * (i % 5), "xGChain": 1.1 * (i % 8),
                "yellow": i % 3, "red": 0, "last_synced_at": iso(NOW)} for i in range(40)]
    form = {"form_score": {"score": 55, "composantes": []},
            "resume": {"matchs": 6, "buts": 3, "passes": 1, "minutes": 480}, "matchs": []}
    bets = [{"_id": m["match_id"], "modele": 2, "competition_code": "PL", "tranche": "5–10", "ecart": 7,
             "fav_side": "home", "fav_odds": 1.8 + 0.1 * k, "model_prob": 0.6, "is_value": k % 2 == 0,
             "commence_time": m["utc_date"], "status": "pending"}
            for k, m in enumerate(x for x in matches if x["competition_code"] == "PL" and x["matchday"] == 8)]
    return matches, table, players, form, bets


@pytest.fixture(scope="module")
def api():
    import motor.motor_asyncio as motor_asyncio
    real_client = motor_asyncio.AsyncIOMotorClient
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MONGO_URL", "mongodb://offline-tests")
        mp.setenv("DB_NAME", "footpulse_offline")
        mp.setenv("COMPETITIONS", "PL,CL")
        mp.setenv("FOOTBALL_DATA_TOKEN", "")
        mp.delenv("ODDS_API_KEY", raising=False)
        motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient
        try:
            import server
        finally:
            motor_asyncio.AsyncIOMotorClient = real_client
        matches, table, players, form, bets = dataset()

        async def seed(db):
            for coll in ("matches", "standings", "players", "player_form", "bets", "meta"):
                await db[coll].delete_many({})
            await db.matches.insert_many(matches)
            await db.standings.insert_one({"competition_code": "PL", "table": table})
            await db.players.insert_many(players)
            await db.player_form.insert_one({"_id": "100", "updated_at": NOW.isoformat(), "data": form})
            await db.bets.insert_many(bets)
            await db.meta.insert_one({"_id": "sync", "last_sync": NOW.isoformat()})
        asyncio.run(seed(server.db))
        # le règlement réel s'appuie sur les matchs de la journée 8 (terminés)
        from routers.stats import settle_bets
        asyncio.run(settle_bets())
        yield TestClient(server.app)


def _upcoming(api):
    dates = api.get("/api/dates", params={"code": "PL"}).json()
    today = NOW.date().isoformat()
    return next(d for d in dates if d >= today)


def test_health_status_competitions(api):
    assert api.get("/api/health").json() == {"ok": True}
    st = api.get("/api/status").json()
    assert st["championnats"] == ["PL", "CL"] and st["matchs_en_base"] == 93 and st["token_present"] is False
    comps = {c["code"]: c["nb_matchs"] for c in api.get("/api/competitions").json()}
    assert comps == {"PL": 90, "CL": 3}


def test_matches_of_the_day(api):
    d = api.get("/api/matches", params={"code": "PL", "date": _upcoming(api)}).json()
    assert d["matchs"]
    for m in d["matchs"]:
        assert m["competition"]["code"] == "PL" and m["status"] == "TIMED"
        assert isinstance(m["domicile"]["global"], int) and isinstance(m["exterieur"]["global"], int)
        if m["calibration"]:
            assert {"ecart", "tranche", "favori", "favori_gagne_pct", "value"} <= set(m["calibration"])


def test_match_detail(api):
    d = api.get("/api/matches", params={"code": "PL", "date": _upcoming(api)}).json()
    detail = api.get(f"/api/match/{d['matchs'][0]['match_id']}").json()
    assert {"match", "domicile", "exterieur", "avantages", "fiabilite", "calibration", "repos",
            "signaux", "confrontations", "joueurs"} <= set(detail)
    assert detail["signaux"]["disponible"] is True and detail["joueurs"]["disponible"] is True
    assert detail["fiabilite"]["niveau"] == "Élevée"
    assert api.get("/api/match/999999").status_code == 404


def test_team_and_leaderboards(api):
    t = api.get("/api/team/PL/1").json()
    assert t["team_id"] == 1 and 0 <= t["global"]["score"] <= 100 and len(t["historique"]) == 8
    assert api.get("/api/team/PL/424242").status_code == 404
    tous = api.get("/api/leaderboard/teams").json()
    assert len(tous) == 20 and {x["competition_code"] for x in tous} == {"PL"}
    assert [x["global"] for x in tous] == sorted((x["global"] for x in tous), reverse=True)
    assert {x["competition_code"] for x in api.get("/api/leaderboard/teams", params={"code": "CL"}).json()} == {"CL"}


def test_players(api):
    lb = api.get("/api/leaderboard/players", params={"tri": "buteurs"}).json()
    buts = [p["stats"]["buts"] for p in lb["joueurs"]]
    assert lb["disponible"] and buts == sorted(buts, reverse=True)
    # logo de l'équipe fourni avec chaque joueur (données football-data de son équipe)
    assert all(pl["team_logo"] == f"https://crests.example/{pl['team_id']}.png" for pl in lb["joueurs"])
    p = api.get("/api/player/100").json()
    assert p["forme_recente"]["form_score"]["score"] == 55
    assert p["team_logo"] == f"https://crests.example/{p['team_id']}.png"
    assert api.get("/api/player/nope").status_code == 404
    assert set(api.post("/api/players/form", json={"ids": ["100", "fm1", "x"]}).json()) == {"100"}
    assert api.post("/api/players/form", json={"ids": "100"}).status_code == 422


def test_search_and_config(api):
    s = api.get("/api/search", params={"q": "man"}).json()
    assert {e["nom_court"] for e in s["equipes"]} == {"Manchester City", "Manchester United"}
    found = api.get("/api/search", params={"q": "Joueur 1"}).json()["joueurs"]
    assert found["disponible"] is True
    assert all(j["team_logo"].startswith("https://crests.example/") for j in found["resultats"])
    conf = api.get("/api/scoring/config").json()
    assert {"equipes", "joueurs"} == set(conf)


def test_stats_and_simulation(api):
    st = api.get("/api/stats").json()
    assert st["disponible"] and st["echantillon"] > 0
    assert [b["tranche"] for b in st["par_ecart_note"]][-1] == "50+"
    sim = api.get("/api/bets/simulation").json()
    assert sim["disponible"] and sim["en_attente"] == 0 and sim["annules"] == 0
    assert sim["strategies"]["favori"]["total"]["paris"] == 10


def test_analyses_cached_then_refreshed_after_sync(api):
    """Les analyses sont servies depuis le cache, puis relues après une synchro."""
    import jobs
    import server
    before = api.get("/api/team/PL/1").json()["stats"]["matchs_analyses"]
    extra = {"match_id": 5000, "competition_code": "PL", "utc_date": "2000-01-01T15:00:00Z",
             "match_date": "2000-01-01", "status": "FINISHED", "matchday": 0,
             "home_team": {"id": 1}, "away_team": {"id": 2}, "score": {"fullTime": {"home": 1, "away": 0}}}
    asyncio.run(server.db.matches.insert_one(extra))
    assert api.get("/api/team/PL/1").json()["stats"]["matchs_analyses"] == before   # cache
    asyncio.run(jobs.run_light_guarded())   # sans jeton : pas d'appel API, mais caches vidés
    assert api.get("/api/team/PL/1").json()["stats"]["matchs_analyses"] == before + 1


def test_startup_without_internal_scheduler(api, monkeypatch):
    """Hébergement en veille : index créés, mais ni planificateur ni synchro au démarrage."""
    import server
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    asyncio.run(server.on_startup())
    assert not server.scheduler.running
    assert "match_id_1" in asyncio.run(server.db.matches.index_information())


def test_sync_command_fails_loudly_without_token(api, capsys):
    """`python -m jobs light` renvoie un code d'erreur si le jeton manque (visible dans le cron)."""
    import jobs
    assert asyncio.run(jobs.main("light")) == 1
    assert "token_manquant" in capsys.readouterr().out
