"""Backend API regression tests for FootPulse Analytics."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/') or 'http://localhost:8001'
# use the public URL from frontend .env
try:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
except Exception:
    pass

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---- /status
def test_status(s):
    r = s.get(f"{API}/status", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["token_present"] is True
    assert d["matchs_en_base"] > 0
    assert isinstance(d["championnats"], list) and len(d["championnats"]) == 7


# ---- /competitions
def test_competitions(s):
    r = s.get(f"{API}/competitions", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert len(d) == 7
    for c in d:
        assert {"code", "nom", "pays", "nb_matchs"} <= set(c.keys())
        assert c["nb_matchs"] >= 0


# ---- /dates
def test_dates_pl(s):
    r = s.get(f"{API}/dates?code=PL", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, list) and len(d) > 0


# ---- /matches
def test_matches_today(s):
    r = s.get(f"{API}/matches", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert "matchs" in d and "date" in d


def test_matches_with_date_and_code(s):
    # find a date with PL matches
    dates = s.get(f"{API}/dates?code=PL", timeout=30).json()
    assert dates
    target = dates[len(dates)//2]
    r = s.get(f"{API}/matches?code=PL&date={target}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["date"] == target
    if d["matchs"]:
        m = d["matchs"][0]
        assert "domicile" in m and "exterieur" in m
        # scores may be None if no history; when present, verify shape
        for side in ("domicile", "exterieur"):
            t = m[side]
            if t and t.get("global") is not None:
                for k in ("global", "offensif", "defensif", "forme"):
                    v = t.get(k)
                    if v is not None:
                        assert 0 <= v <= 100


# ---- /match/{id}
def test_match_detail_and_breakdown_sums(s):
    match_id = 558894
    r = s.get(f"{API}/match/{match_id}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["joueurs"]["disponible"] is False
    assert "confrontations" in d
    assert "signaux" in d
    # signaux should include buts_estimes + avertissement when available
    sig = d["signaux"]
    if sig.get("disponible"):
        assert "buts_estimes" in sig
        assert "avertissement" in sig
        assert isinstance(sig["signaux"], list) and len(sig["signaux"]) >= 4
        for s_ in sig["signaux"]:
            assert {"marche", "statut", "confiance", "explication"} <= set(s_.keys())

    # Verify breakdown sum == score for each analyzed side (transparency)
    for side in ("domicile", "exterieur"):
        team = d.get(side)
        if not team:
            continue
        for key in ("global", "offensif", "defensif", "forme"):
            block = team.get(key)
            if not block:
                continue
            score = block["score"]
            assert 0 <= score <= 100
            total = sum(c.get("contribution", 0) for c in block.get("composantes", []))
            # Allow rounding tolerance (each component rounded independently)
            assert abs(total - score) <= 3, f"{side}.{key} breakdown {total} vs {score}"


def test_match_not_found(s):
    r = s.get(f"{API}/match/999999999", timeout=30)
    assert r.status_code == 404


# ---- /leaderboard
def test_leaderboard_teams_pl_sorted(s):
    r = s.get(f"{API}/leaderboard/teams?code=PL", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, list) and len(d) > 0
    scores = [t["global"] for t in d if t.get("global") is not None]
    assert scores == sorted(scores, reverse=True)


def test_leaderboard_teams_all(s):
    r = s.get(f"{API}/leaderboard/teams", timeout=120)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_leaderboard_players_unavailable(s):
    r = s.get(f"{API}/leaderboard/players", timeout=30)
    assert r.status_code == 200
    assert r.json()["disponible"] is False


# ---- /team
def test_team_detail(s):
    lb = s.get(f"{API}/leaderboard/teams?code=PL", timeout=60).json()
    assert lb
    tid = lb[0]["team_id"]
    r = s.get(f"{API}/team/PL/{tid}", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["team_id"] == tid
    assert "historique" in d and isinstance(d["historique"], list)
    if d["historique"]:
        h = d["historique"][0]
        assert "score_obtenu" in h and 0 <= h["score_obtenu"] <= 100


# ---- /search
def test_search(s):
    r = s.get(f"{API}/search?q=Real", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "equipes" in d
    assert d["joueurs"]["disponible"] is False


# ---- /scoring/config
def test_scoring_config(s):
    r = s.get(f"{API}/scoring/config", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("score_global", "score_offensif", "score_defensif", "donnees_indisponibles"):
        assert k in d
    # weights sum to 1
    assert abs(sum(d["score_global"].values()) - 1.0) < 1e-6
