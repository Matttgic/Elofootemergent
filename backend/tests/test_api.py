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


def test_leaderboard_players_all(s):
    r = s.get(f"{API}/leaderboard/players", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    assert d["min_minutes"] == 180
    players = d["joueurs"]
    assert isinstance(players, list) and len(players) > 0
    # sorted desc by scores.global.score
    scores = [p["scores"]["global"]["score"] for p in players]
    assert scores == sorted(scores, reverse=True)
    # verify Raphinha/Yamal/Mbappe are in top region
    names = [p["nom"].lower() for p in players[:30]]
    top_hits = sum(1 for tgt in ("raphinha", "yamal", "mbapp") if any(tgt in n for n in names))
    assert top_hits >= 2, f"expected 2/3 stars in top 30, got names: {names[:15]}"


def test_leaderboard_players_by_code_pl(s):
    r = s.get(f"{API}/leaderboard/players?code=PL", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    assert all(p["competition_code"] == "PL" for p in d["joueurs"])


def test_leaderboard_players_ppl_unavailable(s):
    r = s.get(f"{API}/leaderboard/players?code=PPL", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is False
    assert "message" in d


def test_player_detail_and_breakdown(s):
    # pick top of PL leaderboard
    lb = s.get(f"{API}/leaderboard/players?code=PL", timeout=60).json()
    pid = lb["joueurs"][0]["player_id"]
    r = s.get(f"{API}/player/{pid}", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["nom"]
    # stats
    stats = d["stats"]
    for k in ("buts", "passes_decisives", "tirs", "occasions_creees", "xG", "xA",
              "cartons_jaunes", "cartons_rouges", "buts_par_90", "minutes"):
        assert k in stats, f"missing stat {k}"
    # scores structure
    for k in ("global", "buteur", "creation", "offensif", "forme"):
        block = d["scores"][k]
        assert 0 <= block["score"] <= 100
        assert isinstance(block["composantes"], list) and len(block["composantes"]) > 0
    # sum of global contributions ≈ score
    gb = d["scores"]["global"]
    total = sum(c.get("contribution", 0) for c in gb["composantes"])
    assert abs(total - gb["score"]) <= 2


def test_match_players_available_pl(s):
    r = s.get(f"{API}/match/560578", timeout=60)
    assert r.status_code == 200
    d = r.json()
    j = d["joueurs"]
    assert j["disponible"] is True
    assert len(j["domicile"]) > 0 and len(j["exterieur"]) > 0
    # sorted desc by score
    for side in ("domicile", "exterieur"):
        scores = [p["scores"]["global"]["score"] for p in j[side]]
        assert scores == sorted(scores, reverse=True)


def test_match_players_unavailable_ded(s):
    # pick a DED match
    dates = s.get(f"{API}/dates?code=DED", timeout=30).json()
    m = s.get(f"{API}/matches?code=DED&date={dates[0]}", timeout=60).json()
    assert m["matchs"]
    mid = m["matchs"][0]["match_id"]
    r = s.get(f"{API}/match/{mid}", timeout=60)
    assert r.status_code == 200
    j = r.json()["joueurs"]
    assert j["disponible"] is False
    assert j.get("message")


def test_search_players(s):
    r = s.get(f"{API}/search?q=Mbapp", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["joueurs"]["disponible"] is True
    res = d["joueurs"]["resultats"]
    assert len(res) > 0
    p = res[0]
    for k in ("player_id", "nom", "poste", "team_title", "score"):
        assert k in p


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
    assert "joueurs" in d


# ---- /scoring/config
def test_scoring_config(s):
    r = s.get(f"{API}/scoring/config", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "equipes" in d and "joueurs" in d
    eq = d["equipes"]
    for k in ("score_global", "score_offensif", "score_defensif", "donnees_indisponibles"):
        assert k in eq
    assert abs(sum(eq["score_global"].values()) - 1.0) < 1e-6
    jo = d["joueurs"]
    for k in ("source", "couverture", "normalisation", "score_joueur", "references_par_90"):
        assert k in jo
