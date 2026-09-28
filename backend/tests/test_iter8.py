"""Iteration 8: confiance, calibration, Poisson 1N2+scores, H2H, repos,
fiche joueur, filtre poste. Regression on core endpoints."""
import pytest
import requests

from backend_url import API

pytestmark = pytest.mark.integration

BIG_FAV_MATCH = 560542  # Arsenal vs Coventry


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---- Match detail: fiabilite, calibration, repos, probabilites ----
def test_match_detail_new_fields(s):
    r = s.get(f"{API}/match/{BIG_FAV_MATCH}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    # fiabilite
    fi = d.get("fiabilite")
    assert fi and fi.get("niveau") in ("Faible", "Moyenne", "Élevée")
    assert "matchs_min" in fi and "message" in fi
    # repos (peut être None)
    assert "repos" in d
    rep = d["repos"]
    assert "domicile" in rep and "exterieur" in rep
    # calibration (peut être None mais ici Arsenal vs Coventry -> attendu)
    cal = d.get("calibration")
    assert cal is not None, "Calibration attendue pour match PL avec écart"
    for k in ("ecart", "tranche", "favori", "favori_gagne_pct", "nul_pct",
              "outsider_gagne_pct", "echantillon"):
        assert k in cal
    # signaux + probabilites
    sig = d["signaux"]
    assert sig["disponible"] is True
    p = sig["probabilites"]
    for k in ("domicile_pct", "nul_pct", "exterieur_pct", "scores_probables"):
        assert k in p
    tot = p["domicile_pct"] + p["nul_pct"] + p["exterieur_pct"]
    assert 97 <= tot <= 103, f"1N2 ne somme pas à ~100: {tot}"
    sp = p["scores_probables"]
    assert len(sp) == 3
    pcts = [x["pct"] for x in sp]
    assert pcts == sorted(pcts, reverse=True), f"scores non décroissants: {pcts}"
    # Gros favori Arsenal -> domicile_pct élevé
    assert p["domicile_pct"] >= 70, f"attendu >=70 pour gros favori, got {p['domicile_pct']}"


def test_match_signals_have_valeur_and_status(s):
    r = s.get(f"{API}/match/{BIG_FAV_MATCH}", timeout=60).json()
    signaux = r["signaux"]["signaux"]
    markets = {x["marche"]: x for x in signaux}
    for m in ("Plus de 2.5 buts", "Plus de 1.5 but", "Moins de 2.5 buts",
              "Les deux équipes marquent (BTTS)"):
        assert m in markets, f"Signal manquant: {m}"
        x = markets[m]
        assert x["valeur"].endswith("%")
        assert x["statut"] in ("Favorable", "Neutre", "Défavorable")
    # Over 2.5 -> Favorable si prob >= 55%
    o25 = markets["Plus de 2.5 buts"]
    val = int(o25["valeur"].rstrip("%"))
    if val >= 55:
        assert o25["statut"] == "Favorable"


def test_h2h_signal_only_if_3plus(s):
    r = s.get(f"{API}/match/{BIG_FAV_MATCH}", timeout=60).json()
    n_conf = len(r.get("confrontations") or [])
    markets = [x["marche"] for x in r["signaux"]["signaux"]]
    has_hist = "Historique direct" in markets
    if n_conf >= 3:
        assert has_hist, "Historique direct devrait apparaître (>=3 confrontations)"
    else:
        assert not has_hist, "Historique direct ne devrait pas apparaître (<3)"


# ---- Leaderboard players filter by poste ----
@pytest.mark.parametrize("poste", ["Attaquant", "Milieu", "Défenseur", "Gardien"])
def test_leaderboard_players_by_poste(s, poste):
    r = s.get(f"{API}/leaderboard/players?tri=buteurs&poste={poste}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    j = d["joueurs"]
    assert len(j) > 0, f"Aucun joueur pour poste {poste}"
    postes = {p["poste"] for p in j}
    assert postes == {poste}, f"Postes non filtrés: {postes}"
    # tri buteurs -> buts décroissants
    buts = [p["stats"]["buts"] for p in j]
    assert buts == sorted(buts, reverse=True)


def test_leaderboard_players_tous(s):
    r = s.get(f"{API}/leaderboard/players?tri=buteurs&poste=Tous", timeout=60).json()
    postes = {p["poste"] for p in r["joueurs"]}
    assert len(postes) >= 2


# ---- Player detail ----
def test_player_detail(s):
    top = s.get(f"{API}/leaderboard/players?tri=buteurs", timeout=60).json()["joueurs"]
    pid = str(top[0]["player_id"])
    r = s.get(f"{API}/player/{pid}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    for k in ("player_id", "nom", "poste", "scores", "stats", "forme_recente"):
        assert k in d
    scores = d["scores"]
    for k in ("global", "buteur", "creation", "offensif", "forme"):
        assert k in scores and "score" in scores[k]
    fr = d["forme_recente"]
    assert fr is not None
    for k in ("form_score", "resume", "matchs"):
        assert k in fr
    for k in ("matchs", "buts", "passes"):
        assert k in fr["resume"]
    assert isinstance(fr["matchs"], list)


# ---- Regression ----
def test_matches_endpoint(s):
    dates = s.get(f"{API}/dates?code=PL", timeout=30).json()
    assert len(dates) > 0
    r = s.get(f"{API}/matches?code=PL&date={dates[0]}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert "matchs" in d


def test_stats_endpoint(s):
    r = s.get(f"{API}/stats", timeout=180)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    tranches = [b["tranche"] for b in d["par_ecart_note"]]
    assert tranches == ["0–5", "5–10", "10–15", "15–20", "20–25", "25–30", "30–35", "35–40", "40–45", "45–50", "50+"]


def test_leaderboard_teams(s):
    r = s.get(f"{API}/leaderboard/teams", timeout=60)
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) > 0


def test_competitions_12(s):
    r = s.get(f"{API}/competitions", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert len(d) == 12


def test_scoring_config(s):
    r = s.get(f"{API}/scoring/config", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "equipes" in d and "joueurs" in d
