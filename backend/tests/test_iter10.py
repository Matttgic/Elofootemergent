"""FootPulse iteration 10: calibration+value on /api/matches, FotMob forme_recente, Understat regression."""
import os
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://match-insights-173.preview.emergentagent.com').rstrip('/')
TIMEOUT = 90
load_dotenv("/app/backend/.env")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- /api/matches calibration + value ----------
def test_matches_calibration_value(s):
    r = s.get(f"{BASE_URL}/api/matches", params={"date": "2026-08-31"}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    matchs = data.get("matchs") or []
    assert len(matchs) > 0, "No matches on 2026-08-31"

    value_seen = False
    for m in matchs:
        cal = m.get("calibration")
        # calibration may be None if a side has no data; but at least most matches must have it
        if cal is None:
            continue
        for k in ("ecart", "favori", "favori_gagne_pct", "nul_pct", "outsider_gagne_pct",
                 "echantillon", "score_frequent", "value"):
            assert k in cal, f"Missing '{k}' in calibration: {cal}"
        sf = cal["score_frequent"]
        if sf is not None:
            assert "score" in sf and "pct" in sf and "n" in sf
            assert 0 <= sf["pct"] <= 100
            assert sf["n"] >= 1
        assert isinstance(cal["value"], bool)
        if cal["value"]:
            value_seen = True
    assert value_seen, "No match with value=true found on 2026-08-31"


# ---------- FotMob player forme_recente NOT null ----------
async def _find_fm_player():
    c = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = c[os.environ['DB_NAME']]
    cur = db.players.find(
        {"competition_code": {"$in": ["DED", "PPL"]}, "minutes": {"$gte": 400}, "goals": {"$gte": 3}},
        {"_id": 0, "player_id": 1, "competition_code": 1, "goals": 1, "minutes": 1, "nom": 1, "player_name": 1},
    ).sort("goals", -1).limit(20)
    docs = await cur.to_list(20)
    return docs


def test_fotmob_forme_recente(s):
    docs = asyncio.new_event_loop().run_until_complete(_find_fm_player())
    assert docs, "No FotMob DED/PPL player with minutes>=400 & goals>=3"
    last_err = None
    for d in docs:
        pid = d["player_id"]
        r = s.get(f"{BASE_URL}/api/player/{pid}", timeout=TIMEOUT)
        if r.status_code != 200:
            last_err = f"{pid}: HTTP {r.status_code} {r.text[:200]}"
            continue
        data = r.json()
        fr = data.get("forme_recente")
        if fr is None:
            last_err = f"{pid}: forme_recente is null"
            continue
        # Validate structure
        fs = fr.get("form_score")
        assert isinstance(fs, dict), f"form_score should be object: {fs}"
        score = fs.get("score")
        assert isinstance(score, int) and 0 <= score <= 100
        comps = fs.get("composantes")
        assert isinstance(comps, list) and len(comps) == 2, f"expected 2 composantes: {comps}"
        # Sum equals form_score (approx)
        total = sum(c.get("contribution", 0) for c in comps)
        assert abs(total - score) <= 2, f"composantes sum {total} != score {score}"
        # Check weights: 55% buts+passes, 45% note
        poids = [c.get("poids") for c in comps]
        assert "55%" in poids and "45%" in poids, f"expected weights 55%/45%, got {poids}"
        resume = fr.get("resume") or {}
        for k in ("matchs", "buts", "passes", "minutes"):
            assert k in resume, f"missing resume.{k}"
        matchs = fr.get("matchs")
        assert isinstance(matchs, list) and len(matchs) > 0, "matchs empty"
        for mm in matchs:
            for k in ("adversaire", "lieu", "buts", "passes", "resultat"):
                assert k in mm, f"match missing {k}: {mm}"
        print(f"OK FotMob player {pid}: score={score}")
        return
    pytest.fail(f"No FotMob player returned valid forme_recente. Last error: {last_err}")


# ---------- Understat regression ----------
async def _find_understat_player():
    c = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = c[os.environ['DB_NAME']]
    cur = db.players.find(
        {"competition_code": {"$in": ["PD", "SA", "BL1", "FL1", "PL"]}, "minutes": {"$gte": 400}, "goals": {"$gte": 3}},
        {"_id": 0, "player_id": 1},
    ).sort("goals", -1).limit(5)
    return await cur.to_list(5)


def test_understat_forme_recente_regression(s):
    docs = asyncio.new_event_loop().run_until_complete(_find_understat_player())
    assert docs, "No Understat player found"
    for d in docs:
        pid = str(d["player_id"])
        assert not pid.startswith("fm")
        r = s.get(f"{BASE_URL}/api/player/{pid}", timeout=TIMEOUT)
        if r.status_code != 200:
            continue
        data = r.json()
        fr = data.get("forme_recente")
        if fr is None:
            continue
        assert "form_score" in fr
        comps = (fr.get("form_score") or {}).get("composantes") or []
        # Understat form has 2 composantes: buts+passes and xG+xA
        assert len(comps) >= 2
        labels = [c.get("libelle", "") for c in comps]
        assert any("xG" in l or "xA" in l for l in labels), f"expected xG/xA composante: {labels}"
        print(f"OK Understat player {pid}: score={fr['form_score'].get('score')}, labels={labels}")
        return
    pytest.fail("No Understat player returned forme_recente")
