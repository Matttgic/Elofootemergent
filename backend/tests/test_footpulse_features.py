"""Backend tests for FootPulse iteration 9: scores_frequents, FotMob player leagues DED/PPL, recalibrated scoring."""
import pytest
import requests

from backend_url import BASE_URL

pytestmark = pytest.mark.integration
TIMEOUT = 60


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- Stats: scores_frequents ----------
def test_stats_scores_frequents_present(s):
    r = s.get(f"{BASE_URL}/api/stats", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert data.get("disponible") is True
    buckets = data.get("par_ecart_elo")
    assert isinstance(buckets, list) and len(buckets) > 0
    for b in buckets:
        if b.get("matchs", 0) > 0:
            sf = b.get("scores_frequents")
            assert isinstance(sf, list), f"scores_frequents missing in bucket {b.get('tranche')}"
            assert len(sf) <= 4
            for item in sf:
                assert "score" in item and isinstance(item["score"], str)
                assert "-" in item["score"]
                assert 0 <= item["pct"] <= 100
                assert item["n"] >= 1


# ---------- Leaderboards: DED, PPL, Regression PL ----------
@pytest.mark.parametrize("code,tri", [("DED", "buteurs"), ("PPL", "global"), ("PL", "global")])
def test_leaderboard_league(s, code, tri):
    r = s.get(f"{BASE_URL}/api/leaderboard/players", params={"code": code, "tri": tri}, timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert data.get("disponible") is True, f"Not disponible for {code}: {data}"
    joueurs = data.get("joueurs", [])
    assert len(joueurs) > 0, f"Empty joueurs for {code}"


def test_leaderboard_all_includes_ded_ppl(s):
    r = s.get(f"{BASE_URL}/api/leaderboard/players", params={"tri": "buteurs"}, timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert data.get("disponible") is True
    joueurs = data.get("joueurs", [])
    assert len(joueurs) > 0
    codes = set()
    for j in joueurs:
        c = j.get("competition_code") or j.get("code_competition") or j.get("competition")
        if c:
            codes.add(c)
    # Try alternate field detection
    print(f"Sample player: {joueurs[0]}")
    print(f"Codes found: {codes}")
    # Must include DED and PPL somewhere
    assert "DED" in codes, f"DED missing. Codes: {codes}"
    assert "PPL" in codes, f"PPL missing. Codes: {codes}"


# ---------- Score sanity ----------
def _check_scores_sane(joueurs):
    for j in joueurs:
        scores = j.get("scores") or {}
        for key in ("global", "buteur", "creation", "offensif"):
            entry = scores.get(key)
            if entry is None:
                continue
            val = entry.get("score") if isinstance(entry, dict) else entry
            if val is None:
                continue
            assert 0 <= val <= 100, f"Score {key}={val} out of range for player {j.get('nom')}"


@pytest.mark.parametrize("code", ["DED", "PPL", "PL"])
def test_player_scores_within_bounds(s, code):
    r = s.get(f"{BASE_URL}/api/leaderboard/players", params={"code": code, "tri": "global"}, timeout=TIMEOUT)
    assert r.status_code == 200
    _check_scores_sane(r.json().get("joueurs", []))


# ---------- Match endpoint: DED (FotMob) ----------
def _get_finished_match_id(s, code):
    # Query MongoDB directly since /api/matches is date-scoped
    import asyncio, os as _os
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parents[1] / ".env")
    async def _q():
        c = AsyncIOMotorClient(_os.environ['MONGO_URL'])
        db = c[_os.environ['DB_NAME']]
        d = await db.matches.find_one({"competition_code": code, "status": "FINISHED"}, {"match_id": 1, "_id": 0})
        return d and d.get("match_id")
    return asyncio.get_event_loop().run_until_complete(_q()) if False else asyncio.new_event_loop().run_until_complete(_q())


def test_match_ded_fotmob_players(s):
    mid = _get_finished_match_id(s, "DED")
    assert mid, "No DED match id found"
    r = s.get(f"{BASE_URL}/api/match/{mid}", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    joueurs = data.get("joueurs", {})
    assert joueurs.get("disponible") is True, f"Players not available: {joueurs}"
    src = (joueurs.get("source") or "").lower()
    assert "fotmob" in src, f"Source should contain FotMob, got: {joueurs.get('source')}"
    dom = joueurs.get("domicile", []) or []
    ext = joueurs.get("exterieur", []) or []
    assert len(dom) + len(ext) > 0
    for p in (dom + ext):
        gs = (p.get("scores") or {}).get("global")
        val = gs.get("score") if isinstance(gs, dict) else gs
        if val is not None:
            assert 0 <= val <= 100


def test_match_pl_understat_regression(s):
    mid = _get_finished_match_id(s, "PL")
    assert mid, "No PL match id found"
    r = s.get(f"{BASE_URL}/api/match/{mid}", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    joueurs = data.get("joueurs", {})
    assert joueurs.get("disponible") is True
    src = (joueurs.get("source") or "").lower()
    assert "understat" in src, f"Source should contain Understat, got: {joueurs.get('source')}"


# ---------- Player endpoint: FotMob (fm-prefixed) ----------
def test_player_fotmob_endpoint(s):
    # Get a FotMob player from DED leaderboard
    r = s.get(f"{BASE_URL}/api/leaderboard/players", params={"code": "DED", "tri": "global"}, timeout=TIMEOUT)
    joueurs = r.json().get("joueurs", [])
    fm_player = None
    for j in joueurs:
        pid = str(j.get("player_id") or j.get("id") or "")
        if pid.startswith("fm"):
            fm_player = pid
            break
    assert fm_player, f"No FotMob player found. Sample: {joueurs[0] if joueurs else None}"
    r2 = s.get(f"{BASE_URL}/api/player/{fm_player}", timeout=TIMEOUT)
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data.get("scores") is not None
    # forme_recente should be None/null for FotMob
    assert data.get("forme_recente") is None, f"forme_recente must be null, got: {data.get('forme_recente')}"
