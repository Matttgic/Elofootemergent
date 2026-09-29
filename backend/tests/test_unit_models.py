"""Tests unitaires hors ligne (ni réseau ni base) : Elo et probabilités 1N2,
rapprochement cotes <-> matchs et mises Kelly."""
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from betting import (KELLY_CAP, clv_pct, kelly_fraction, match_fixture, settle_outcome,  # noqa: E402
                     simulate, team_similarity, value_bets, value_pick)
from elo import (DEFAULT_LOGIT, fit_ordered_logit, fit_outcome_model, margin_multiplier,  # noqa: E402
                 outcome_probs, run_elo)
from player_ingest import build_team_map  # noqa: E402
from scoring import compute_defensif, compute_offensif  # noqa: E402
from signals import _align_split, _poisson_probs, build_signals  # noqa: E402
from teamnames import normalize_team_name  # noqa: E402


def _match(mid, date, hid, aid, gh=None, ga=None, home=None, away=None):
    return {
        "match_id": mid, "utc_date": date,
        "status": "FINISHED" if gh is not None else "TIMED",
        "home_team": {"id": hid, **(home or {})}, "away_team": {"id": aid, **(away or {})},
        "score": {"fullTime": {"home": gh, "away": ga}},
    }


def _random_league(seed, n_teams=18, rounds=8):
    """Ligue où toutes les équipes ont le même niveau : résultats purement aléatoires."""
    rng = random.Random(seed)

    def pois(lam):
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p < limit:
                return k
            k += 1

    teams, matches, mid = list(range(1, n_teams + 1)), [], 0
    for r in range(rounds):
        rng.shuffle(teams)
        for i in range(0, n_teams, 2):
            mid += 1
            matches.append(_match(mid, f"2026-08-{r + 1:02d}T15:00:00Z", teams[i], teams[i + 1],
                                  pois(1.45), pois(1.15)))
    return matches


# ---------------------------------------------------------------------------
# Elo et probabilités 1N2 (pas de fuite de données)
# ---------------------------------------------------------------------------
def test_elo_pre_ratings_ignore_the_match_itself_and_later_ones():
    matches = _random_league(seed=1)
    pre = run_elo(matches)["pre"]
    target = next(m for m in matches if "2026-08-04" < m["utc_date"] < "2026-08-06")

    altered = [dict(m) for m in matches]
    for m in altered:
        if m["match_id"] == target["match_id"] or m["utc_date"] > target["utc_date"]:
            m["score"] = {"fullTime": {"home": 9, "away": 0}}
    assert run_elo(altered)["pre"][target["match_id"]] == pre[target["match_id"]]


def test_elo_is_zero_sum_and_counts_home_advantage():
    r = run_elo([_match(1, "2026-08-01T15:00:00Z", 1, 2, 1, 1)])
    # nul à domicile entre équipes égales : le domicile (favori) perd des points
    assert r["ratings"][1] < 1500 < r["ratings"][2]
    assert r["ratings"][1] + r["ratings"][2] == 3000
    assert r["pre"][1] == (1500, 1500, 0) and r["played"] == {1: 1, 2: 1}
    assert margin_multiplier(1) == 1 and margin_multiplier(2) == 1.5 and margin_multiplier(-4) == 15 / 8


def test_newcomer_starts_among_the_weakest_of_its_league():
    matches = _random_league(seed=3)
    for m in matches:
        m["competition_code"] = "PL"
    late = _match(999, "2026-09-01T15:00:00Z", 77, 1, 0, 0)
    late["competition_code"] = "PL"
    r = run_elo(matches + [late])
    pool = sorted(r["pre"][m["match_id"]][0] for m in matches if m["utc_date"] >= "2026-08-08")
    assert r["pre"][999][0] < sorted(r["ratings"][t] for t in range(1, 19))[9]
    assert pool and r["pre"][999][0] != 1500


def test_random_league_elo_favourite_not_inflated():
    """Sur des résultats purement aléatoires, l'équipe au meilleur Elo ne doit pas
    gagner nettement plus qu'elle ne perd (pas de fuite du résultat dans la note)."""
    v = d = 0
    for seed in range(60):
        matches = _random_league(seed)
        pre = run_elo(matches)["pre"]
        for m in matches:
            rh, ra, n = pre[m["match_id"]]
            gh, ga = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
            if n < 3 or rh == ra or gh == ga:
                continue
            if (gh > ga) == (rh > ra):
                v += 1
            else:
                d += 1
    assert abs(v - d) / (v + d) < 0.1, (v, d)


def test_ordered_logit_recovers_known_coefficients():
    rng = random.Random(5)
    true = {"beta": 0.7, "theta_away": -0.5, "theta_draw": 0.6}
    xs, ys = [], []
    for _ in range(6000):
        x = rng.uniform(-3, 3)
        u = rng.random()
        p_away = 1 / (1 + math.exp(-(true["theta_away"] - true["beta"] * x)))
        p_nh = 1 / (1 + math.exp(-(true["theta_draw"] - true["beta"] * x)))
        xs.append(x)
        ys.append(0 if u < p_away else (1 if u < p_nh else 2))
    fit = fit_ordered_logit(xs, ys)
    for k, v in true.items():
        assert abs(fit[k] - v) < 0.08, (k, fit)


def test_outcome_probabilities_sum_to_one_and_follow_the_gap():
    probs = [outcome_probs(d) for d in (-300, -100, 0, 100, 300)]
    for ph, pn, pa in probs:
        assert abs(ph + pn + pa - 1) < 1e-9 and min(ph, pn, pa) > 0
    homes = [p[0] for p in probs]
    assert homes == sorted(homes) and probs[2][0] > probs[2][2]   # avantage du terrain à écart nul


def test_fit_outcome_model_needs_enough_matches():
    matches = _random_league(seed=4)
    pre = run_elo(matches)["pre"]
    model = fit_outcome_model(matches, pre)
    assert model["ajuste"] is False and model["beta"] == DEFAULT_LOGIT["beta"]


def test_goal_split_aligned_on_elo_keeps_total():
    home = _align_split(2.6, 0.30)
    P = _poisson_probs(home, 2.6 - home)
    assert abs((P["domicile"] - P["exterieur"]) - 0.30) < 1e-3
    # total inchangé : plus de 2.5 buts identique (aux troncatures de la grille près)
    assert abs(P["over25"] - _poisson_probs(1.3, 1.3)["over25"]) < 1e-3


def test_closing_line_value():
    assert clv_pct(2.2, 2.0) == 10.0 and clv_pct(1.8, 2.0) == -10.0
    assert clv_pct(2.0, None) is None and clv_pct(None, 2.0) is None


def test_value_strategy_settles_the_chosen_issue():
    bets = [
        {"status": "lost", "resultat": "draw", "commence_time": "t1", "tranche": "40–50 %",
         "value": {"issue": "nul", "cote": 3.4, "proba_pct": 33.0}},     # favori perdu, mais nul joué gagné
        {"status": "won", "resultat": "home", "commence_time": "t2", "tranche": "50–60 %",
         "value": {"issue": "exterieur", "cote": 4.0, "proba_pct": 28.0}},
        {"status": "void", "resultat": None, "commence_time": "t3", "value": {"issue": "nul", "cote": 3.0, "proba_pct": 35.0}},
        {"status": "won", "resultat": "home", "commence_time": "t4", "value": None},
    ]
    out = value_bets(bets)
    assert [(b["status"], b["fav_odds"]) for b in out] == [("won", 3.4), ("lost", 4.0)]
    assert simulate(out)["mise_fixe"]["gain_net"] == 1.4


def test_value_pick_needs_a_real_edge():
    pred = {"domicile_pct": 50.0, "nul_pct": 25.0, "exterieur_pct": 25.0}
    assert value_pick(pred, {"home_odds": 1.9, "draw_odds": 3.5, "away_odds": 4.0}) is None
    v = value_pick(pred, {"home_odds": 2.3, "draw_odds": 3.5, "away_odds": 4.0})
    assert v == {"issue": "domicile", "cote": 2.3, "proba_pct": 50.0, "avantage_pct": 15.0}
    assert value_pick(None, {"home_odds": 2.3}) is None and value_pick(pred, None) is None


# ---------------------------------------------------------------------------
# Rapprochement cotes <-> matchs
# ---------------------------------------------------------------------------
MUN = {"name": "Manchester United FC", "shortName": "Man United"}
MCI = {"name": "Manchester City FC", "shortName": "Man City"}
ARS = {"name": "Arsenal FC", "shortName": "Arsenal"}
CHE = {"name": "Chelsea FC", "shortName": "Chelsea"}
RMA = {"name": "Real Madrid CF", "shortName": "Real Madrid"}
RSO = {"name": "Real Sociedad de Fútbol", "shortName": "Real Sociedad"}
GET = {"name": "Getafe CF", "shortName": "Getafe"}
ALA = {"name": "Deportivo Alavés", "shortName": "Alavés"}


def _fx(home, away, when):
    return {"home_team": home, "away_team": away, "commence_time": when}


def test_team_similarity_prefers_the_right_club():
    assert team_similarity("Manchester United", MUN) > team_similarity("Manchester United", MCI)
    assert team_similarity("Real Madrid", RMA) > team_similarity("Real Madrid", RSO)
    assert team_similarity("Inter Milan", {"name": "FC Internazionale Milano", "shortName": "Inter"}) >= 0.9
    assert team_similarity("Bayern Munich", {"name": "FC Bayern München", "shortName": "Bayern"}) >= 0.9


def test_fixture_picks_same_weekend_match_among_similar_names():
    matches = [
        _match(1, "2026-10-03T14:00:00Z", 10, 11, home=MCI, away=CHE),
        _match(2, "2026-10-04T15:30:00Z", 12, 13, home=MUN, away=ARS),
    ]
    assert match_fixture(_fx("Manchester United", "Arsenal", "2026-10-04T15:30:00Z"), matches)["match_id"] == 2
    matches = [
        _match(3, "2026-10-04T12:00:00Z", 20, 21, home=RSO, away=ALA),
        _match(4, "2026-10-04T19:00:00Z", 22, 23, home=RMA, away=GET),
    ]
    assert match_fixture(_fx("Real Madrid", "Getafe", "2026-10-04T19:00:00Z"), matches)["match_id"] == 4


def test_fixture_ignores_matches_outside_the_kickoff_window():
    # le derby retour (dans 5 mois) ne doit pas capter les cotes du match aller
    reverse = _match(5, "2027-03-07T16:00:00Z", 11, 10, home=MCI, away=MUN)
    assert match_fixture(_fx("Manchester United", "Manchester City", "2026-10-04T15:30:00Z"), [reverse]) is None
    first_leg = _match(6, "2026-10-04T15:30:00Z", 10, 11, home=MUN, away=MCI)
    fx = _fx("Manchester United", "Manchester City", "2026-10-04T15:30:00Z")
    assert match_fixture(fx, [reverse, first_leg])["match_id"] == 6


def test_fixture_rejects_unknown_teams_and_missing_kickoff():
    matches = [_match(7, "2026-10-04T15:30:00Z", 12, 13, home=MUN, away=ARS)]
    assert match_fixture(_fx("Everton", "Arsenal", "2026-10-04T15:30:00Z"), matches) is None
    assert match_fixture(_fx("Manchester United", "Arsenal", None), matches) is None


# ---------------------------------------------------------------------------
# Kelly fractionné plafonné
# ---------------------------------------------------------------------------
def test_kelly_fraction_is_quarter_and_capped():
    assert kelly_fraction(0.5, 1.8) == 0.0                    # aucun avantage
    assert math.isclose(kelly_fraction(0.55, 2.0), 0.25 * 0.10)
    assert kelly_fraction(0.9, 3.0) == KELLY_CAP               # plein Kelly = 85 % -> plafonné
    assert kelly_fraction(0.9, 1.0) == 0.0 and kelly_fraction(None, 2.0) == 0.0


def _bet(status, odds, p, when):
    return {"status": status, "fav_odds": odds, "model_prob": p, "commence_time": when}


def test_simulate_compounds_and_never_goes_negative():
    bets = [_bet("won", 3.0, 0.9, "2026-10-01T15:00:00Z"), _bet("lost", 3.0, 0.9, "2026-10-02T15:00:00Z")]
    k = simulate(bets)["kelly"]
    # 100 -> +5 % misé à cote 3 = 110 -> -5 % de 110 = 104.5
    assert k["bankroll"] == 104.5 and k["mise_totale"] == 10.5
    many = [_bet("lost", 3.0, 0.9, "2026-10-03T15:00:00Z") for _ in range(40)]
    assert simulate(many)["kelly"]["bankroll"] >= 0


def test_simulate_flat_stake_unchanged():
    t = simulate([_bet("won", 2.5, 0.6, "a"), _bet("lost", 1.5, 0.6, "b")])
    assert t["paris"] == 2 and t["gagnes"] == 1 and t["taux_reussite"] == 50.0
    assert t["mise_fixe"] == {"mise_totale": 2.0, "gain_net": 0.5, "roi": 25.0, "bankroll": 100.5}


# ---------------------------------------------------------------------------
# Règlement des paris (reports / annulations)
# ---------------------------------------------------------------------------
KICK = "2026-10-04T15:00:00Z"
NOW_SAME_DAY = datetime(2026, 10, 4, 18, tzinfo=timezone.utc)
NOW_LATER = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)   # > 72 h après l'horaire prévu


def _fd(status, gh=None, ga=None, date=KICK):
    return {"status": status, "utc_date": date, "score": {"fullTime": {"home": gh, "away": ga}}}


def test_settle_finished_match():
    home_bet = {"fav_side": "home", "commence_time": KICK}
    assert settle_outcome(home_bet, _fd("FINISHED", 2, 1), NOW_SAME_DAY) == "won"
    assert settle_outcome(home_bet, _fd("FINISHED", 1, 1), NOW_SAME_DAY) == "lost"
    assert settle_outcome({"fav_side": "away", "commence_time": KICK}, _fd("FINISHED", 0, 3), NOW_SAME_DAY) == "won"


def test_settle_voids_cancelled_and_postponed_matches():
    bet = {"fav_side": "home", "commence_time": KICK}
    assert settle_outcome(bet, _fd("CANCELLED"), NOW_SAME_DAY) == "void"
    assert settle_outcome(bet, _fd("POSTPONED"), NOW_SAME_DAY) is None       # encore dans le délai
    assert settle_outcome(bet, _fd("POSTPONED"), NOW_LATER) == "void"
    assert settle_outcome(bet, _fd("TIMED", date="2026-12-01T20:00:00Z"), NOW_LATER) == "void"  # reprogrammé
    assert settle_outcome(bet, None, NOW_LATER) == "void"
    # reporté puis joué 5 jours plus tard : annulé, pas réglé sur le nouveau match
    assert settle_outcome(bet, _fd("FINISHED", 2, 0, date="2026-10-09T19:00:00Z"), NOW_LATER) == "void"
    assert settle_outcome(bet, _fd("TIMED"), NOW_SAME_DAY) is None


# ---------------------------------------------------------------------------
# Notes équipe : ajustement adversaire symétrique
# ---------------------------------------------------------------------------
def test_defence_adjusted_for_opponent_strength_like_attack():
    pos_map = {10: (1, 20), 11: (20, 20)}   # 10 = leader, 11 = lanterne rouge
    vs_strong = [{"gf": 1, "gc": 2, "opponent_id": 10} for _ in range(5)]
    vs_weak = [{"gf": 1, "gc": 2, "opponent_id": 11} for _ in range(5)]
    assert compute_defensif(vs_strong, pos_map)["score"] > compute_defensif(vs_weak, pos_map)["score"]
    assert compute_offensif(vs_strong, pos_map)["score"] > compute_offensif(vs_weak, pos_map)["score"]


# ---------------------------------------------------------------------------
# Poisson : moyennes ramenées vers la moyenne du championnat
# ---------------------------------------------------------------------------
def test_poisson_expectations_shrunk_towards_league_average():
    # 1 seul match chacun : l'équipe 1 a gagné 3-0 à domicile, l'équipe 2 a perdu 3-0 à l'extérieur.
    # Sans rétrécissement : 3 × 3 / 1.45 = 6.2 buts attendus (plafonné à 3.5).
    matches = [_match(1, "2026-08-01T15:00:00Z", 1, 3, 3, 0), _match(2, "2026-08-01T15:00:00Z", 4, 2, 3, 0)]
    est = build_signals(matches, 1, 2, "A", "B", 1.45, 1.15)["buts_estimes"]
    # (3 + 4×1.45)/5 = 1.76 marqués et encaissés -> 1.76 × 1.76 / 1.45
    assert est["domicile"] == round(1.76 * 1.76 / 1.45, 2)
    assert est["exterieur"] == round(0.92 * 0.92 / 1.15, 2)


# ---------------------------------------------------------------------------
# Noms d'équipe (normalisation commune, rapprochements)
# ---------------------------------------------------------------------------
def test_team_name_normalisation():
    assert normalize_team_name("1. FC Köln") == "koln"
    assert normalize_team_name("Real Betis Balompié") == "real betis"
    assert normalize_team_name("TSG 1899 Hoffenheim") == normalize_team_name("TSG Hoffenheim") == "hoffenheim"
    assert normalize_team_name("FK Bodø/Glimt") == "fk bodo glimt"
    assert normalize_team_name(None) == ""


def test_psg_not_confused_with_paris_fc_whatever_the_order():
    teams = [{"id": 1, "name": "Paris Saint-Germain FC", "shortName": "PSG", "tla": "PSG"},
             {"id": 2, "name": "Paris FC", "shortName": "Paris FC", "tla": "PFC"}]
    for order in (teams, teams[::-1]):
        assert build_team_map(["Paris Saint Germain", "Paris FC"], order) == {"Paris Saint Germain": 1, "Paris FC": 2}


def test_odds_names_with_aliases():
    rennes, nantes = {"name": "Stade Rennais FC 1901", "shortName": "Stade Rennais"}, {"name": "FC Nantes", "shortName": "Nantes"}
    assert team_similarity("Rennes", rennes) == 1.0 > team_similarity("Rennes", nantes)
    inter = {"name": "FC Internazionale Milano", "shortName": "Inter"}
    milan = {"name": "AC Milan", "shortName": "Milan"}
    assert team_similarity("Inter Milan", inter) > team_similarity("Inter Milan", milan)


def test_competitions_default_to_all_free_tier(monkeypatch):
    from ingest import COMPETITION_META, configured_codes
    monkeypatch.delenv("COMPETITIONS", raising=False)
    assert configured_codes() == list(COMPETITION_META) and len(configured_codes()) == 12
    monkeypatch.setenv("COMPETITIONS", "pl, CL ,XYZ")
    assert configured_codes() == ["PL", "CL"]
