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
    for m in matches:
        if m["competition_code"] == "PL" and m["status"] == "FINISHED":
            h, a = m["home_team"]["id"], m["away_team"]["id"]
            m["xg"] = {"home": round(strength[h] * rng.uniform(0.6, 1.4), 2),
                       "away": round(strength[a] * rng.uniform(0.6, 1.4), 2), "source": "understat"}
    players = [{"player_id": str(100 + i), "competition_code": "PL", "season": 2026,
                "nom": f"Joueur {i}", "position": ["F", "M", "D", "GK"][i % 4],
                "team_title": team(1 + i % 20)["shortName"], "team_id": 1 + i % 20,
                "games": 8, "minutes": 200 + 80 * i, "goals": i % 7, "assists": i % 5, "shots": 3 * (i % 9),
                "key_passes": 2 * (i % 6), "xG": 0.6 * (i % 7), "xA": 0.4 * (i % 5), "xGChain": 1.1 * (i % 8),
                "yellow": i % 3, "red": 0, "last_synced_at": iso(NOW)} for i in range(40)]
    form = {"form_score": {"score": 55, "composantes": []},
            "resume": {"matchs": 6, "buts": 3, "passes": 1, "minutes": 480}, "matchs": []}
    bets = [{"_id": m["match_id"], "modele": 4, "competition_code": "PL", "tranche": "50–60 %", "ecart": 70,
             "fav_side": "home", "fav_odds": 1.8 + 0.1 * k, "model_prob": 0.6, "is_value": k % 2 == 0,
             "home_odds": 1.8 + 0.1 * k, "draw_odds": 3.6, "away_odds": 4.2, "bookmaker": "betclic_fr",
             "value": {"issue": "nul", "cote": 3.6, "proba_pct": 30.0, "avantage_pct": 8.0} if k % 2 == 0 else None,
             "cotes_recentes": {"domicile": 1.8, "nul": 3.4, "exterieur": 4.4} if k < 10 else None,
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
                                                   "away": min(6, int(rng.expovariate(1 / strength[a])))}},
                            "xg": {"home": round(strength[h] * rng.uniform(0.6, 1.4), 2),
                                   "away": round(strength[a] * rng.uniform(0.6, 1.4), 2)}})
    # équipe de la saison précédente absente cette saison (reléguée hors des championnats suivis)
    gone = {"id": 21, "name": "Ipswich Town FC", "shortName": "Ipswich Town", "tla": "IPS",
            "crest": "https://crests.example/21.png"}
    kick = NOW.replace(hour=15) - timedelta(days=200)
    history.append({"match_id": 59999, "competition_code": "PL", "season": NOW.year - 1, "utc_date": iso(kick),
                    "match_date": kick.date().isoformat(), "matchday": 20, "status": "FINISHED",
                    "home_team": gone, "away_team": team(1), "score": {"fullTime": {"home": 0, "away": 2}}})
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
        # xG disponibles pour les deux équipes : modèle Elo + xG
        assert p["modele"] == "Elo + xG" and p["xg_domicile"] is not None
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
    assert t["elo"]["sur"] == 20      # l'équipe reléguée hors des championnats suivis n'est pas classée
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


def test_compare_two_teams(api):
    d = api.get("/api/compare", params={"a": "PL-1", "b": "PL-4"}).json()
    assert d["a"]["team_id"] == 1 and d["b"]["team_id"] == 4 and d["a"]["elo"]["championnat"] == "PL"
    for key in ("a_recoit", "b_recoit"):
        p = d[key]
        assert abs(p["domicile_pct"] + p["nul_pct"] + p["exterieur_pct"] - 100) < 0.5
    # l'avantage du terrain profite à celle qui reçoit
    assert d["a_recoit"]["domicile_pct"] > d["b_recoit"]["exterieur_pct"]
    assert d["confrontations"] and d["a"]["elo_historique"]
    assert api.get("/api/compare", params={"a": "PL-1", "b": "PL"}).status_code == 422
    assert api.get("/api/compare", params={"a": "PL-1", "b": "PL-4242"}).status_code == 404


def test_search_and_config(api):
    s = api.get("/api/search", params={"q": "man"}).json()
    assert {e["nom_court"] for e in s["equipes"]} == {"Manchester City", "Manchester United"}
    found = api.get("/api/search", params={"q": "Joueur 1"}).json()["joueurs"]
    assert found["disponible"] is True
    assert all(j["team_logo"].startswith("https://crests.example/") for j in found["resultats"])
    conf = api.get("/api/scoring/config").json()
    assert {"equipes", "joueurs", "elo"} == set(conf)
    assert conf["elo"]["backtest"]["log_loss"][2]["modele"] == "Elo"
    ranking = conf["elo"]["backtest"]["classement"]["methodes"]
    site = next(m for m in ranking if m.get("site"))
    assert site["modele"].startswith("Pronostic FootPulse") and site["indice"] == 86
    assert {m["id"]: m["indice"] for m in ranking}["frequences"] == 0 and ranking[0]["indice"] == 100
    notes_bt = conf["elo"]["backtest"]["notes"]
    assert [r["modele"] for r in notes_bt["log_loss"]][0] == "Note /100 seule" and notes_bt["conclusion"]


def test_stats_and_simulation(api):
    st = api.get("/api/stats").json()
    assert st["disponible"] and st["echantillon"] > st["echantillon_saison"] > 0
    assert [b["tranche"] for b in st["par_ecart_elo"]][-1] == "200+"
    fav = st["favori_elo"]
    assert abs(fav["victoires_pct"] + fav["nuls_pct"] + fav["defaites_pct"] - 100) < 0.5
    q = st["modele"]
    assert q["matchs"] == st["echantillon_saison"] and 0 < q["modele"]["log_loss"] < 2
    assert q["avec_xg_pct"] > 90
    assert sum(c["matchs"] for c in q["calibration"]) == q["matchs"]
    # la note /100 seule, évaluée comme modèle sur les mêmes matchs de la saison
    qn = q["note_100"]
    # (saison précédente trop courte ici pour ajuster la note seule : ajustement sur la saison)
    assert 0 < qn["matchs"] <= q["matchs"] and qn["hors_echantillon"] is False
    for k in ("modele", "note", "reference"):
        assert 0 < qn[k]["log_loss"] < 2 and 0 < qn[k]["brier"] < 1.5
    # écart des notes /100 avant-match, saison précédente comprise, selon le terrain
    notes = st["notes"]
    assert notes["disponible"] and notes["echantillon"] > notes["echantillon_saison"] > 0
    split = notes["mieux_notee"]
    assert split["tous"]["matchs"] == split["domicile"]["matchs"] + split["exterieur"]["matchs"] == notes["echantillon"]
    for venue in ("tous", "domicile", "exterieur"):
        rows = notes["par_ecart"][venue]
        assert [r["tranche"] for r in rows][-1] == "40+" and rows[-1]["max"] is None
        assert sum(r["matchs"] for r in rows) == split[venue]["matchs"]
    # la fiche match retrouve la tranche de son écart et le terrain de la mieux notée
    row = max(notes["par_ecart"]["exterieur"], key=lambda r: r["matchs"])
    assert row["matchs"] >= 20
    h = api.get("/api/stats/ecart-notes", params={"domicile": 50, "exterieur": 51 + row["min"]}).json()["historique"]
    assert (h["tranche"], h["terrain"], h["ecart"], h["matchs"]) == (row["tranche"], "exterieur", row["min"] + 1, row["matchs"])
    assert api.get("/api/stats/ecart-notes", params={"domicile": 60, "exterieur": 60}).json()["historique"] is None
    assert api.get("/api/stats/ecart-notes", params={"domicile": 101, "exterieur": 60}).status_code == 422
    sim = api.get("/api/bets/simulation").json()
    # journée 8 jouée (10 paris réglés), journée 9 à venir (10 en attente)
    assert sim["disponible"] and sim["en_attente"] == 10 and sim["annules"] == 0
    assert sim["strategies"]["favori"]["total"]["paris"] == 10
    assert [b["tranche"] for b in sim["strategies"]["favori"]["par_ecart"]] == ["50–60 %"]
    # stratégie value : l'issue repérée (ici le nul) sur les 5 matchs concernés
    val = sim["strategies"]["value"]
    assert val["total"]["paris"] == 5
    # valeur de clôture : cote obtenue vs dernière cote relevée
    assert sim["strategies"]["favori"]["clv"]["paris"] == 10
    assert sim["strategies"]["value"]["clv"]["moyenne_pct"] == round((3.6 / 3.4 - 1) * 100, 2)


def test_settle_backfills_value_from_snapshot_odds(api):
    """Un pari v3 figé sans issue « value » la reçoit, calculée avec les cotes et
    probabilités du moment du pari."""
    import server
    from routers.stats import settle_bets

    async def scenario():
        db = server.db
        base = {"modele": 4, "status": "pending", "commence_time": "2099-01-01T15:00:00Z", "tranche": "40–50 %",
                "probas": {"domicile": 38.3, "nul": 28.6, "exterieur": 33.1}}
        await db.bets.insert_many([
            {**base, "_id": 990001, "home_odds": 3.35, "draw_odds": 3.03, "away_odds": 2.03},
            {**base, "_id": 990002, "home_odds": 2.4, "draw_odds": 3.2, "away_odds": 2.9},
        ])
        await settle_bets()
        docs = {d["_id"]: d async for d in db.bets.find({"_id": {"$in": [990001, 990002]}})}
        await db.bets.delete_many({"_id": {"$in": [990001, 990002]}})
        return docs

    docs = asyncio.run(scenario())
    assert docs[990001]["value"] == {"issue": "domicile", "cote": 3.35, "proba_pct": 38.3, "avantage_pct": 28.3}
    assert "value" in docs[990002] and docs[990002]["value"] is None


def test_bets_lists(api):
    pending = api.get("/api/bets").json()["paris"]
    settled = api.get("/api/bets", params={"statut": "regles"}).json()["paris"]
    assert len(pending) == 10 and len(settled) == 10
    assert [p["date"] for p in pending] == sorted(p["date"] for p in pending)
    first = settled[0]
    assert first["domicile"]["nom"] and first["score"]["home"] is not None and first["statut"] in ("won", "lost")
    assert first["favori"]["issue"] == "domicile" and first["favori"]["clv_pct"] is not None
    assert all(p["score"] is None for p in pending)


def test_snapshot_creates_v3_bets_and_tracks_latest_odds(api, monkeypatch):
    """Prise de paris avec des cotes simulées : un nouveau pari v3 (issue value comprise)
    pour un match sans pari, et mise à jour des cotes récentes des paris déjà figés."""
    import server
    from routers import stats as stats_router

    async def scenario():
        db = server.db
        upcoming = await db.matches.find({"competition_code": "PL", "matchday": 9}, {"_id": 0}).to_list(20)
        target = upcoming[0]
        await db.bets.delete_one({"_id": target["match_id"]})

        async def fake_odds(sport):
            return [{"home_team": m["home_team"]["name"], "away_team": m["away_team"]["name"],
                     "commence_time": m["utc_date"], "home_odds": 2.5, "draw_odds": 3.3, "away_odds": 3.1,
                     "bookmaker": "winamax_fr"} for m in upcoming]

        monkeypatch.setattr(stats_router, "fetch_odds", fake_odds)
        monkeypatch.setattr(stats_router, "ODDS_SPORT", {"PL": "soccer_epl"})
        monkeypatch.setenv("ODDS_API_KEY", "cle-test")
        res = await stats_router.snapshot_bets()
        created = await db.bets.find_one({"_id": target["match_id"]})
        other = await db.bets.find_one({"_id": upcoming[1]["match_id"]})
        return res, created, other

    res, created, other = asyncio.run(scenario())
    assert res == {"ok": True, "crees": 1, "cotes_actualisees": 9}
    assert created["modele"] == 4 and created["status"] == "pending" and created["bookmaker"] == "winamax_fr"
    assert abs(sum(created["probas"].values()) - 100) < 0.5
    if created["value"]:
        assert created["value"]["avantage_pct"] >= 5
    assert other["cotes_recentes"]["domicile"] == 2.5 and other["cotes_recentes"]["bookmaker"] == "winamax_fr"


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


def test_light_and_full_ingest_write_matches_in_bulk(api, monkeypatch):
    """Synchros légère et complète avec un client football-data simulé : matchs
    écrits (upsert groupé), historique chargé, classement et date de synchro."""
    import ingest
    import server

    def item(mid, code, day, season=2026):
        return {"id": mid, "utcDate": f"{season}-10-{day:02d}T15:00:00Z", "status": "SCHEDULED", "matchday": 9,
                "competition": {"code": code}, "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
                "score": {"fullTime": {"home": None, "away": None}}, "season": {"startDate": f"{season}-08-01"}}

    class FakeClient:
        def __init__(self, token):
            pass

        async def matches_window(self, start, end):
            return {"matches": [item(70001, "PL", 3), item(70002, "PL", 4), item(70003, "BL1", 4)]}

        async def competition_matches(self, code, season=None):
            if season:
                return {"matches": [item(80000 + season, code, 5, season)]}
            return {"filters": {"season": "2026"}, "matches": [item(70001, code, 3), item(70004, code, 5)]}

        async def standings(self, code):
            return {"season": {"id": 1}, "standings": [{"type": "TOTAL", "table": []}]}

        async def close(self):
            pass

    async def no_players(db):
        return {"ok": True}

    monkeypatch.setenv("FOOTBALL_DATA_TOKEN", "jeton-test")
    monkeypatch.setenv("COMPETITIONS", "PL")
    monkeypatch.setattr(ingest, "FootballDataClient", FakeClient)
    monkeypatch.setattr(ingest, "ingest_players", no_players)
    monkeypatch.setattr(ingest, "ingest_fotmob_players", no_players)

    async def no_xg(db, now=None):
        return {"appels": 0}

    import xg_ingest
    monkeypatch.setattr(xg_ingest, "ingest_xg", no_xg)

    async def scenario():
        db = server.db
        await db.meta.delete_one({"_id": "history"})
        standings = await db.standings.find_one({"competition_code": "PL"}, {"_id": 0})
        light = await ingest.run_light_ingest(db)
        full = await ingest.run_ingest(db)
        ids = {m["match_id"] async for m in db.matches.find({"match_id": {"$gte": 70000, "$lt": 71000}})}
        hist = await db.matches_history.count_documents({"match_id": {"$in": [82025, 82024]}})
        await db.matches.delete_many({"match_id": {"$gte": 70000, "$lt": 71000}})
        await db.matches_history.delete_many({"match_id": {"$in": [82025, 82024]}})
        await db.meta.update_one({"_id": "sync"}, {"$set": {"last_sync": NOW.isoformat()}})
        await db.standings.replace_one({"competition_code": "PL"}, standings)
        return light, full, ids, hist

    light, full, ids, hist = asyncio.run(scenario())
    assert light["ok"] and light["matchs_maj"] == 2          # BL1 hors des compétitions suivies
    assert full["ok"] and full["matchs"] == 2 and full["historique"] == 2
    assert ids == {70001, 70002, 70004} and hist == 2


def test_xg_ingest_attaches_understat_xg(api, monkeypatch):
    """xG Understat rattachés aux matchs (saison en cours et précédentes) par équipes
    et date ± 1 jour ; saisons précédentes chargées une seule fois."""
    import server
    import xg_ingest
    calls = []

    async def fake_fetch(league, season):
        calls.append((league, season))
        coll = server.db.matches if season == xg_ingest.current_season() else server.db.matches_history
        docs = await coll.find({"competition_code": "PL", "status": "FINISHED",
                                "home_team.name": {"$exists": True}}).to_list(1000)
        # noms « à la Understat » (sans « FC »), heure décalée d'un jour pour la moitié
        return [{"datetime": (m["utc_date"][:10] if i % 2 else
                              (datetime.fromisoformat(m["utc_date"][:10]) - timedelta(days=1)).date().isoformat())
                 + " 20:00:00",
                 "h": {"title": m["home_team"]["name"].replace(" FC", "")},
                 "a": {"title": m["away_team"]["name"].replace(" FC", "")},
                 "xG": {"h": "1.5", "a": "0.5"}} for i, m in enumerate(docs)]

    async def scenario():
        db = server.db
        await db.meta.delete_one({"_id": "xg"})
        first = await xg_ingest.ingest_xg(db)
        again = await xg_ingest.ingest_xg(db)
        cur = await db.matches.count_documents({"xg.source": "understat", "xg.home": 1.5})
        hist = await db.matches_history.count_documents({"xg.source": "understat", "xg.home": 1.5})
        return first, again, cur, hist

    monkeypatch.setattr(xg_ingest, "fetch_league_matches", fake_fetch)
    monkeypatch.setattr(xg_ingest, "current_season", lambda: NOW.year)
    monkeypatch.setenv("COMPETITIONS", "PL")
    first, again, cur, hist = asyncio.run(scenario())
    assert first["rattaches"] == cur + hist and cur == 80 and hist >= 190 and first["non_rattaches"] == 0
    # 2e synchro : seule la saison en cours est relue
    assert again["appels"] == 1 and calls.count(("EPL", NOW.year)) == 2


def test_sync_command_fails_loudly_without_token(api, capsys):
    """`python -m jobs light` renvoie un code d'erreur si le jeton manque (visible dans le cron)."""
    import jobs
    assert asyncio.run(jobs.main("light")) == 1
    assert "token_manquant" in capsys.readouterr().out
