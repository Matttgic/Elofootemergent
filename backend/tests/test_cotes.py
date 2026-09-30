"""Tests hors ligne de la page « Cotes » : recherche des matchs aux cotes voisines et
des équipes à cote de victoire voisine (petit historique construit à la main), puis
le fichier réel de l'historique Pinnacle et les routes de l'API (sans base)."""
import gzip
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cotes_historiques as ch  # noqa: E402
from routers import cotes as cotes_router  # noqa: E402

# (ligue, date, domicile, extérieur, buts dom, buts ext, cotes)
ROWS = [
    ("F1", 20200101, "Paris SG", "Nantes", 3, 0, (1.30, 5.80, 10.5)),
    ("F1", 20200201, "Paris SG", "Lille", 1, 1, (1.31, 5.60, 10.0)),
    ("I1", 20210101, "Inter", "Lazio", 0, 1, (1.29, 5.90, 11.0)),
    ("F1", 20210301, "Lyon", "Paris SG", 0, 2, (10.0, 5.70, 1.32)),      # PSG favori à l'extérieur
    ("F1", 20220101, "Paris SG", "Lens", 2, 0, (1.60, 4.00, 5.50)),       # trop loin
    ("F1", 20220201, "Lens", "Marseille", 1, 1, (2.40, 3.30, 3.10)),
]


@pytest.fixture(scope="module")
def small():
    return ch.Historique(ROWS)


def test_fair_probs_remove_margin():
    p, marge = ch.fair_probs((2.0, 2.0))
    assert p == [0.5, 0.5] and marge == pytest.approx(0.0)
    p, marge = ch.fair_probs((1.30, 5.75, 10.5))
    assert sum(p) == pytest.approx(1.0) and marge == pytest.approx(1 / 1.3 + 1 / 5.75 + 1 / 10.5 - 1)


def test_similar_odds_counts_outcomes_and_returns(small):
    s = ch.similaires(small, (1.30, 5.75, 10.5), precision=5)
    assert s["matchs"] == 3 and s["identiques"] == 0      # le 5e match (1,60) et Lyon-PSG sont exclus
    dom, nul, ext = (s["issues"][k] for k in ch.ISSUES)
    assert (dom["matchs"], nul["matchs"], ext["matchs"]) == (1, 1, 1)
    assert dom["reel_pct"] == pytest.approx(33.3) and dom["seuil_pct"] == pytest.approx(76.9)
    # rendement à la cote demandée : 1/3 × 1,30 − 1 ; historique : +0,30 − 1 − 1 sur 3 paris
    assert dom["rendement_pct"] == pytest.approx(-56.7) and dom["roi_historique_pct"] == pytest.approx(-56.7)
    assert ext["roi_historique_pct"] == pytest.approx(100 * (11.0 - 1 - 2) / 3, abs=0.1)
    assert s["suffisant"] is False
    assert s["cotes_pinnacle"] == [1.30, 5.77, 10.5]      # moyenne des cotes des 3 matchs trouvés
    assert [e["date"] for e in s["exemples"]] == ["2021-01-01", "2020-02-01", "2020-01-01"]
    assert s["exemples"][0] == {"date": "2021-01-01", "ligue": "Serie A", "domicile": "Inter", "exterieur": "Lazio",
                                "score": "0-1", "cotes": [1.29, 5.9, 11.0]}
    # cotes identiques comptées à part ; précision plus large : le match à 1,60 reste loin
    assert ch.similaires(small, (1.30, 5.80, 10.5))["identiques"] == 1
    assert ch.similaires(small, (1.30, 5.75, 10.5), precision=25)["matchs"] == 3


def test_other_bookmaker_margin_is_removed(small):
    # mêmes probabilités avec 8 % de marge (cotes d'un bookmaker français) : mêmes voisins
    q, _ = ch.fair_probs((1.30, 5.75, 10.5))
    cotes = tuple(round(1 / (x * 1.08), 3) for x in q)
    s = ch.similaires(small, cotes)
    assert s["matchs"] == 3 and s["cotes_pinnacle"][0] > cotes[0]     # cotes Pinnacle plus hautes (moins de marge)
    assert ch.similaires(small, (1.80, 3.60, 4.20))["cotes_pinnacle"] is None


def test_team_at_similar_win_odds_any_venue(small):
    psg = ch.trouver_equipe(small, "paris sg")
    assert psg is not None and ch.trouver_equipe(small, "Inconnu FC") is None
    e = ch.equipe_a_cote(small, psg, 1.30, cote_adverse=10.5, cote_nul=5.75)
    assert e["nom"] == "Paris SG" and e["matchs"] == 3 and e["domicile"] == 2      # dont Lyon-PSG à l'extérieur
    assert (e["victoire_pct"], e["nul_pct"], e["defaite_pct"]) == (66.7, 33.3, 0.0)
    assert e["cote_min"] == 1.30 and e["cote_max"] == 1.32 and e["ligues"] == ["Ligue 1"]
    assert e["roi_historique_pct"] == pytest.approx(100 * (0.30 + 0.32 - 1) / 3, abs=0.1)
    assert {x["terrain"] for x in e["exemples"]} == {"domicile", "exterieur"}


def test_full_search_and_team_list(small):
    r = ch.recherche(small, (1.30, 5.75, 10.5), 5, "Paris SG", "Nobody")
    assert r["probas_cotes"]["domicile"] == pytest.approx(74.1) and r["marge_pct"] == pytest.approx(3.8)
    assert r["equipe_domicile"]["matchs"] == 3
    assert (r["equipe_domicile"]["victoires"], r["equipe_domicile"]["nuls"], r["equipe_domicile"]["defaites"]) == (2, 1, 0)
    assert r["equipe_exterieur"] == {"nom": "Nobody", "trouvee": False}
    # tendance : 3 matchs aux cotes voisines (1-0, 1-1, 0-1) + Lyon-PSG (PSG gagne à l'extérieur,
    # compté comme une victoire de l'équipe qui reçoit ici) ; PSG-Nantes et PSG-Lille comptés une fois
    t = r["tendance"]
    assert (t["matchs"], t["domicile"], t["nul"], t["exterieur"]) == (4, 2, 1, 1) and t["issue"] == "domicile"
    assert t["domicile_pct"] == 50.0
    # sans équipe connue : pas de tendance ; Lens reçoit à 2,40, Marseille se déplace à 3,10
    assert ch.recherche(small, (1.30, 5.75, 10.5))["tendance"] is None
    t = ch.recherche(small, (2.40, 3.30, 3.10), 5, "Nantes", "Marseille")["tendance"]
    assert (t["matchs"], t["nul"]) == (1, 1)            # Lens-Marseille 1-1, trouvé deux fois, compté une fois
    noms = [e["nom"] for e in ch.liste_equipes(small)]
    assert noms == sorted(noms, key=str.lower) and "Marseille" in noms
    assert next(e for e in ch.liste_equipes(small) if e["nom"] == "Paris SG")["matchs"] == 4


def test_calibration_buckets(small):
    # 70 fois l'historique : seule la tranche 1,25-1,35 à domicile atteint 200 matchs (3 × 70)
    dom = ch.calibration(ch.Historique(ROWS * 70))["domicile"]
    assert [(r["cote_min"], r["cote_max"], r["matchs"]) for r in dom] == [(1.25, 1.35, 210)]
    assert dom[0]["reel_pct"] == pytest.approx(33.3) and dom[0]["annonce_pct"] == pytest.approx(74.3, abs=0.3)


def test_real_history_file():
    h = ch.historique()
    assert h is not None and len(h) > 150_000 and len(h.ligues) == 38
    assert h.periode()[0] < "2013" and h.periode()[1] >= "2025-12"
    with gzip.open(ch.DATA, "rt", encoding="utf-8") as f:
        assert f.readline().strip().split(",") == ch.COLONNES
    # Pinnacle est bien calibré : fréquences réelles proches des probabilités annoncées
    s = ch.similaires(h, (2.10, 3.40, 3.60))
    assert s["matchs"] > 3000
    for v in s["issues"].values():
        assert abs(v["reel_pct"] - v["annonce_pct"]) < 2.5
    psg = ch.equipe_a_cote(h, ch.trouver_equipe(h, "Paris SG"), 1.30)
    assert psg["matchs"] > 50 and psg["ligues"] == ["Ligue 1"]


@pytest.fixture(scope="module")
def api():
    app = FastAPI()
    app.include_router(cotes_router.router)
    return TestClient(app)


def test_api_similar_odds(api):
    r = api.get("/api/cotes/similaires", params={"domicile": 1.30, "nul": 5.75, "exterieur": 10.5,
                                                 "equipe_domicile": "Paris SG", "equipe_exterieur": "Marseille"})
    assert r.status_code == 200
    d = r.json()
    assert d["similaires"]["matchs"] > 100 and d["similaires"]["precision_pct"] == ch.PRECISION
    assert d["equipe_domicile"]["nom"] == "Paris SG" and d["equipe_exterieur"]["trouvee"] is True
    t = d["tendance"]
    assert t["issue"] == "domicile" and t["matchs"] >= d["similaires"]["matchs"]
    assert t["domicile"] + t["nul"] + t["exterieur"] == t["matchs"]
    assert d["historique"]["championnats"] == 38
    # cotes irréalistes (marge de 42 %) ou hors bornes : refusées
    assert api.get("/api/cotes/similaires", params={"domicile": 1.2, "nul": 3, "exterieur": 4}).status_code == 422
    assert api.get("/api/cotes/similaires", params={"domicile": 1, "nul": 3, "exterieur": 4}).status_code == 422
    r = api.get("/api/cotes/similaires", params={"domicile": 2.8, "nul": 3.6, "exterieur": 4.2})   # marge de −13 %
    assert r.status_code == 422 and "à coup sûr" in r.json()["detail"]
    assert api.get("/api/cotes/similaires", params={"domicile": 2, "nul": 3.4, "exterieur": 3.6,
                                                    "precision": 50}).status_code == 422


def test_api_teams_and_calibration(api):
    eq = api.get("/api/cotes/equipes").json()["equipes"]
    assert len(eq) > 1000 and any(e["nom"] == "Paris SG" for e in eq)
    c = api.get("/api/cotes/calibration").json()
    assert set(c["calibration"]) == set(ch.ISSUES) and c["test"] == ch.TEST_HISTORIQUE
    assert all(r["matchs"] >= ch.CAL_MIN for rows in c["calibration"].values() for r in rows)
