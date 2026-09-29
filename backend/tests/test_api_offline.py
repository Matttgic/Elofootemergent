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
    bets = [{"_id": m["match_id"], "modele": 3, "competition_code": "PL", "tranche": "50–60 %", "ecart": 70,
             "fav_side": "home", "fav_odds": 1.8 + 0.1 * k, "model_prob": 0.6, "is_value": k % 2 == 0,
             "home_odds": 1.8 + 0.1 * k, "draw_odds": 3.6, "away_odds": 4.2, "bookmaker": "betclic_fr",
             "commence_time": m["utc_date"], "status": "pending"}
            for k, m in enumerate(x for x in matches if x["competition_code"] == "PL" and x["matchday"] in (8, 9))]
    # saison précédente (19 journées) : historique Elo et confrontations directes
    history = []
    for r in range(19):
        ids = list(range(1, 21))
        rng.shuffle(ids)
        kick = NOW.replace(hour=15) - timedelta(days=365 - 7 * r)
        for i in range(0, 20, 2):
            h, a = ids[i], ids[i + 1]
            history.append({"match_id": 50000 + 10 * r + i // 2, "competition_code": "PL", "season": NOW.year - 1,
                            "utc_date": iso(kick), "match_date": kick.date().isoformat(), "matchday": r + 1,
                            "status": "FINISHED", "home_team": team(h), "away_team": team(a),
                            "score": {"fullTime": {"home": min(6, int(rng.expovariate(1 / strength[h]))),
                                                   "away": min(6, int(rng.expovariate(1 / strength[a])))}}})
    return matches, table, players, form, bets, history


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
        matches, table, players, form, bets, history = dataset()

        async def seed(db):
            for coll in ("matches", "matches_history", "standings", "players", "player_form", "bets", "meta"):
                await db[coll].delete_many({})
            await db.matches.insert_many(matches)
            await db.matches_history.insert_many(history)
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
        p = m["prediction"]
        assert abs(p["domicile_pct"] + p["nul_pct"] + p["exterieur_pct"] - 100) < 0.5
        assert p["fiable"] is True and p["matchs_min"] >= 10     # saison précédente comprise
        assert p["favori_pct"] == max(p["domicile_pct"], p["exterieur_pct"])
        # cotes figées de la journée 9 : affichées, « value » seulement si l'avantage atteint 5 %
        assert m["cotes"]["bookmaker"] == "betclic_fr"
        if m["value"]:
            assert m["value"]["avantage_pct"] >= 5


def test_match_detail(api):
    d = api.get("/api/matches", params={"code": "PL", "date": _upcoming(api)}).json()
    detail = api.get(f"/api/match/{d['matchs'][0]['match_id']}").json()
    assert {"match", "domicile", "exterieur", "avantages", "fiabilite", "prediction", "cotes", "value",
            "repos", "signaux", "confrontations", "joueurs"} <= set(detail)
    assert detail["signaux"]["disponible"] is True and detail["joueurs"]["disponible"] is True
    assert detail["fiabilite"]["niveau"] == "Élevée"
    # probabilités affichées = Elo ; scores probables tirés d'une loi de Poisson alignée dessus
    pred, probas = detail["prediction"], detail["signaux"]["probabilites"]
    assert probas["source"] == "Elo" and probas["domicile_pct"] == round(pred["domicile_pct"])
    assert detail["domicile"]["elo"]["elo"] == pred["elo_domicile"] and detail["domicile"]["elo"]["sur"] == 20
    assert detail["confrontations"]   # saison précédente comprise
    assert api.get("/api/match/999999").status_code == 404


def test_team_and_leaderboards(api):
    t = api.get("/api/team/PL/1").json()
    assert t["team_id"] == 1 and 0 <= t["global"]["score"] <= 100 and len(t["historique"]) == 8
    assert t["elo"]["championnat"] == "PL" and 1 <= t["elo"]["rang"] <= 20
    assert len(t["elo_historique"]) == t["elo"]["matchs"] and round(t["elo_historique"][-1]["elo"]) == t["elo"]["elo"]
    assert api.get("/api/team/PL/424242").status_code == 404
    tous = api.get("/api/leaderboard/teams").json()
    assert len(tous) == 20 and {x["competition_code"] for x in tous} == {"PL"}
    assert [x["elo"] for x in tous] == sorted((x["elo"] for x in tous), reverse=True)
    par_note = api.get("/api/leaderboard/teams", params={"tri": "note"}).json()
    assert [x["global"] for x in par_note] == sorted((x["global"] for x in par_note), reverse=True)
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
    assert {"equipes", "joueurs", "elo"} == set(conf)
    assert conf["elo"]["backtest"]["log_loss"][2]["modele"] == "Elo (site)"


def test_stats_and_simulation(api):
    st = api.get("/api/stats").json()
    assert st["disponible"] and st["echantillon"] > st["echantillon_saison"] > 0
    assert [b["tranche"] for b in st["par_ecart_elo"]][-1] == "200+"
    fav = st["favori_elo"]
    assert abs(fav["victoires_pct"] + fav["nuls_pct"] + fav["defaites_pct"] - 100) < 0.5
    q = st["modele"]
    assert q["matchs"] == st["echantillon_saison"] and 0 < q["modele"]["log_loss"] < 2
    assert sum(c["matchs"] for c in q["calibration"]) == q["matchs"]
    sim = api.get("/api/bets/simulation").json()
    # journée 8 jouée (10 paris réglés), journée 9 à venir (10 en attente)
    assert sim["disponible"] and sim["en_attente"] == 10 and sim["annules"] == 0
    assert sim["strategies"]["favori"]["total"]["paris"] == 10
    assert [b["tranche"] for b in sim["strategies"]["favori"]["par_ecart"]] == ["50–60 %"]


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


def test_catch_up_when_data_is_stale(api, monkeypatch):
    """Rattrapage léger en arrière-plan si la synchro a plus de 2 h, au plus 1×/30 min."""
    import jobs
    import server
    calls = []

    async def fake_light():
        calls.append(1)
        return {"ok": True}

    async def scenario(last_sync):
        await server.db.meta.update_one({"_id": "sync"}, {"$set": {"last_sync": last_sync}})
        started = await jobs.catch_up_if_stale()
        await asyncio.sleep(0)   # laisse la tâche d'arrière-plan s'exécuter
        return started

    monkeypatch.setattr(jobs, "run_light_guarded", fake_light)
    monkeypatch.setitem(jobs._catch_up, "last_attempt", None)
    fresh = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert asyncio.run(scenario(old)) is False            # sans jeton : rien
    monkeypatch.setenv("FOOTBALL_DATA_TOKEN", "jeton-test")
    assert asyncio.run(scenario(fresh)) is False          # données récentes
    assert asyncio.run(scenario(old)) is True and calls == [1]
    assert asyncio.run(scenario(old)) is False            # déjà tenté il y a moins de 30 min
    asyncio.run(server.db.meta.update_one({"_id": "sync"}, {"$set": {"last_sync": NOW.isoformat()}}))


def test_history_seasons_loaded_once_and_refusal_retried_later(api):
    """Saisons précédentes : chargées une fois ; un refus (403 de l'offre gratuite)
    est mémorisé et ne sera retenté qu'après 7 jours."""
    import httpx
    import ingest
    import server

    class FakeClient:
        def __init__(self):
            self.calls = []

        async def competition_matches(self, code, season=None):
            self.calls.append((code, season))
            if season == 2023:
                raise httpx.HTTPStatusError("403", request=httpx.Request("GET", "http://x"),
                                            response=httpx.Response(403))
            return {"matches": [{"id": 90000 + season, "utcDate": f"{season}-09-01T15:00:00Z",
                                 "status": "FINISHED", "matchday": 1, "homeTeam": {"id": 1},
                                 "awayTeam": {"id": 2}, "score": {"fullTime": {"home": 1, "away": 0}}}]}

    async def scenario():
        db = server.db
        await db.meta.delete_one({"_id": "history"})
        fake = FakeClient()
        first = await ingest.ingest_history(db, fake, "PL", 2025)
        again = await ingest.ingest_history(db, fake, "PL", 2025)
        later = await ingest.ingest_history(db, fake, "PL", 2025, now=datetime.now(timezone.utc) + timedelta(days=8))
        skipped = await ingest.ingest_history(db, fake, "WC", 2026)
        meta = (await db.meta.find_one({"_id": "history"}))["saisons"]
        doc = await db.matches_history.find_one({"match_id": 92024})
        await db.matches_history.delete_one({"match_id": 92024})
        return first, again, later, skipped, fake.calls, meta, doc

    first, again, later, skipped, calls, meta, doc = asyncio.run(scenario())
    assert (first, again, later, skipped) == (1, 0, 0, 0)
    assert calls == [("PL", 2024), ("PL", 2023), ("PL", 2023)]   # 2024 acquis, 2023 retenté après 7 j
    assert meta["PL-2024"]["statut"] == "ok" and meta["PL-2023"] == {**meta["PL-2023"], "statut": "refuse", "http": 403}
    assert doc["season"] == 2024 and doc["competition_code"] == "PL"
    assert ingest._season_year({"filters": {"season": "2026"}}) == 2026
    assert ingest._season_year({"matches": [{"season": {"startDate": "2025-08-15"}}]}) == 2025


def test_sync_command_fails_loudly_without_token(api, capsys):
    """`python -m jobs light` renvoie un code d'erreur si le jeton manque (visible dans le cron)."""
    import jobs
    assert asyncio.run(jobs.main("light")) == 1
    assert "token_manquant" in capsys.readouterr().out
