"""Backtest du modèle Elo sur l'historique football-data.co.uk (résultats + cotes).

Télécharge (une fois, dans un cache local) les saisons 2019-20 à aujourd'hui de 8
championnats européens, puis compare, saison par saison et sans regarder l'avenir
(coefficients 1N2 ajustés sur les seules saisons précédentes) :
  - les probabilités 1N2 du modèle Elo du site ;
  - de simples fréquences domicile / nul / extérieur (référence naïve) ;
  - les cotes des bookmakers (Bet365 avant-match, moyenne et Pinnacle à la clôture) ;
et simule des stratégies de paris aux cotes Bet365.

    cd backend && python -m tools.backtest_historique [--k 20] [--home-adv 60] [--xg]

Réseau requis ; ne tourne pas dans la CI. Résultats de référence (septembre 2026,
13 273 matchs de 2021-22 à 2026-27) : log-loss Elo 0,990 ; fréquences 1,073 ;
Bet365 0,971 ; Pinnacle clôture 0,967. Aucune stratégie n'est rentable face aux
cotes réelles (favori du modèle −4,6 %, « value » de −8,8 % à −13,9 %).

--xg : rattache aussi les xG Understat des 5 grands championnats et compare, sur
ces championnats, l'Elo seul et le modèle Elo + forme xG du site (référence :
7 800 matchs, log-loss 0,992 → 0,983 ; Pinnacle 0,968).

--notes : évalue la note /100 du site comme modèle 1N2 (écart des notes globales avant
le match), seule ou ajoutée à l'Elo, sur les matchs où les deux notes existent
(référence : 11 740 matchs, note 1,022 ; Elo 0,9915 ; Elo + note 0,9912 ; Pinnacle 0,970).

--classement : toutes les méthodes sur les mêmes matchs (5 grands championnats où xG,
notes et cotes existent), avec l'indice de précision de la page Méthode (0 = simples
fréquences, 100 = Pinnacle ; référence : 7 144 matchs, pronostic du site 86, Elo 77,
note /100 49, Bet365 98).
"""
import argparse
import csv
import gzip
import io
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import elo  # noqa: E402

LEAGUES = ["E0", "E1", "SP1", "I1", "D1", "F1", "P1", "N1"]   # PL, Championship, Liga, Serie A, BL, L1, Portugal, NL
SEASONS = ["1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"]
TEST = SEASONS[2:]            # 1re saison : rodage de l'Elo ; 2e : premier ajustement 1N2
CACHE = Path(os.environ.get("BACKTEST_CACHE", Path.home() / ".cache" / "footpulse-backtest"))
URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def _csv(season, league):
    path = CACHE / f"{league}_{season}.csv"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL.format(season=season, league=league), timeout=60) as r:
            path.write_bytes(r.read())
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _odds(row, *cols):
    try:
        v = [float(row[c]) for c in cols]
    except (KeyError, TypeError, ValueError):
        return None
    return v if all(x > 1 for x in v) else None


def load():
    rows = []
    for season in SEASONS:
        for league in LEAGUES:
            for r in csv.DictReader(io.StringIO(_csv(season, league))):
                if not r.get("HomeTeam") or not r.get("FTHG"):
                    continue
                dd, mm, yy = r["Date"].split("/")
                yy = "20" + yy if len(yy) == 2 else yy
                rows.append({
                    "match_id": len(rows) + 1, "competition_code": league, "season": season,
                    "utc_date": f"{yy}-{mm}-{dd}T{(r.get('Time') or '15:00')[:5]}:00Z", "status": "FINISHED",
                    "home_team": {"id": r["HomeTeam"]}, "away_team": {"id": r["AwayTeam"]},
                    "score": {"fullTime": {"home": int(r["FTHG"]), "away": int(r["FTAG"])}},
                    "b365": _odds(r, "B365H", "B365D", "B365A"),
                    "avg_close": _odds(r, "AvgCH", "AvgCD", "AvgCA"),
                    "ps_close": _odds(r, "PSCH", "PSCD", "PSCA"),
                })
    return rows


US_LEAGUES = {"E0": "EPL", "SP1": "La_liga", "I1": "Serie_A", "D1": "Bundesliga", "F1": "Ligue_1"}
US_URL = "https://understat.com/getLeagueData/{league}/{year}"


def _understat(league, year):
    path = CACHE / f"understat_{league}_{year}.json"
    if not path.exists():
        req = urllib.request.Request(US_URL.format(league=league, year=year), headers={
            "X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0",
            "Referer": f"https://understat.com/league/{league}/{year}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    return [d for d in json.loads(path.read_text())["dates"] if d.get("isResult")]


def attach_xg(rows):
    """Ajoute m["xg"] aux matchs des 5 grands championnats (mêmes règles que la synchro)."""
    from xg_ingest import attach_xg_ops
    by_key = {}
    for m in rows:
        if m["competition_code"] in US_LEAGUES:
            m["home_team"]["name"], m["away_team"]["name"] = m["home_team"]["id"], m["away_team"]["id"]
            by_key.setdefault((m["competition_code"], m["season"]), []).append(m)
    by_id = {m["match_id"]: m for m in rows}
    linked = total = 0
    for (league, season), ms in by_key.items():
        ops, _ = attach_xg_ops(_understat(US_LEAGUES[league], 2000 + int(season[:2])), ms)
        for op in ops:
            by_id[op._filter["match_id"]]["xg"] = op._doc["$set"]["xg"]
        linked, total = linked + len(ops), total + len(ms)
    return linked, total


def outcome(m):
    ft = m["score"]["fullTime"]
    return 0 if ft["home"] > ft["away"] else (1 if ft["home"] == ft["away"] else 2)   # index dans (dom, nul, ext)


def book(odds):
    inv = [1 / o for o in odds]
    return [x / sum(inv) for x in inv]


def scores(pairs):
    ll = br = hit = 0.0
    for p, y in pairs:
        ll -= math.log(max(p[y], 1e-12))
        br += sum((p[i] - (i == y)) ** 2 for i in range(3))
        hit += max(range(3), key=lambda i: p[i]) == y
    n = len(pairs)
    return f"log-loss {ll / n:.4f} · Brier {br / n:.4f} · réussite {hit / n * 100:.1f} % ({n} matchs)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=float, default=elo.K)
    ap.add_argument("--home-adv", type=float, default=elo.HOME_ADV)
    ap.add_argument("--xg", action="store_true", help="comparer aussi le modèle Elo + forme xG")
    ap.add_argument("--notes", action="store_true", help="évaluer la note /100 seule et le modèle Elo + note")
    ap.add_argument("--classement", action="store_true", help="classer toutes les méthodes sur les mêmes matchs")
    args = ap.parse_args()

    rows = load()
    pre = elo.run_elo(rows, k=args.k, home_adv=args.home_adv)["pre"]
    if args.xg:
        backtest_xg(rows, pre, args.home_adv)
        return
    if args.notes:
        backtest_notes(rows, pre, args.home_adv)
        return
    if args.classement:
        backtest_ranking(rows, pre, args.home_adv)
        return
    preds = {"Fréquences dom/nul/ext": [], "Elo (site)": [], "Bet365 avant-match": [],
             "Moyenne clôture": [], "Pinnacle clôture": []}
    bets = []
    for season in TEST:
        train = [m for m in rows if SEASONS[0] < m["season"] < season]
        coefs = elo.fit_outcome_model(train, pre, home_adv=args.home_adv)
        base = [sum(outcome(m) == y for m in train) / len(train) for y in range(3)]
        for m in rows:
            if m["season"] != season or not (m["b365"] and m["avg_close"] and m["ps_close"]):
                continue
            rh, ra, _ = pre[m["match_id"]]
            p = list(elo.outcome_probs(rh - ra, coefs, home_adv=args.home_adv))
            y = outcome(m)
            for name, probs in (("Fréquences dom/nul/ext", base), ("Elo (site)", p),
                                ("Bet365 avant-match", book(m["b365"])), ("Moyenne clôture", book(m["avg_close"])),
                                ("Pinnacle clôture", book(m["ps_close"]))):
                preds[name].append((probs, y))
            bets.append((p, m["b365"], y))

    print(f"Elo K={args.k:g}, avantage du terrain {args.home_adv:g} — saisons {TEST[0]} à {TEST[-1]}")
    for name, pairs in preds.items():
        print(f"  {name:24} {scores(pairs)}")

    print("Paris simulés aux cotes Bet365 (1 unité par pari) :")

    def run(label, pick):
        n = won = 0
        pnl = 0.0
        for p, odds, y in bets:
            i = pick(p, odds)
            if i is None:
                continue
            n += 1
            won += i == y
            pnl += odds[i] - 1 if i == y else -1
        print(f"  {label:34} {n:6} paris · réussite {won / max(n, 1) * 100:5.1f} % · ROI {pnl / max(n, 1) * 100:+6.2f} %")

    run("Favori du modèle", lambda p, o: max(range(3), key=lambda i: p[i]))
    for edge in (0.0, 0.05, 0.10, 0.20):
        def value(p, o, edge=edge):
            ev = [p[i] * o[i] - 1 for i in range(3)]
            i = max(range(3), key=lambda j: ev[j])
            return i if ev[i] >= edge else None
        run(f"Value (avantage ≥ {edge * 100:.0f} %)", value)


def backtest_xg(rows, pre, home_adv):
    linked, total = attach_xg(rows)
    print(f"xG rattachés : {linked} / {total} matchs des 5 grands championnats")
    xgf = elo.xg_form(rows)
    preds = {"Elo seul": [], "Elo + forme xG (site)": [], "Pinnacle clôture": []}
    for season in TEST:
        train = [m for m in rows if SEASONS[0] < m["season"] < season]
        c1 = elo.fit_outcome_model(train, pre, home_adv=home_adv)
        c2 = elo.fit_outcome_model_xg(train, pre, xgf, home_adv=home_adv)
        for m in rows:
            if (m["season"] != season or m["competition_code"] not in US_LEAGUES or not m["ps_close"]
                    or pre[m["match_id"]][2] < elo.BURN_IN):
                continue
            rh, ra, _ = pre[m["match_id"]]
            d = elo.xg_diff(*xgf["pre"][m["match_id"]])
            p1 = list(elo.outcome_probs(rh - ra, c1, home_adv=home_adv))
            p2 = list(elo.outcome_probs(rh - ra, c2, home_adv=home_adv, xg_diff=d)) if d is not None else p1
            for name, probs in (("Elo seul", p1), ("Elo + forme xG (site)", p2), ("Pinnacle clôture", book(m["ps_close"]))):
                preds[name].append((probs, outcome(m)))
    print(f"5 grands championnats — saisons {TEST[0]} à {TEST[-1]}")
    for name, pairs in preds.items():
        print(f"  {name:24} {scores(pairs)}")


def backtest_notes(rows, pre, home_adv):
    """La note /100 comme modèle 1N2 (logit ordonné sur l'écart des notes globales avant le
    match, recalculées championnat par championnat et saison par saison), seule ou ajoutée
    à l'Elo."""
    from scoring import pre_match_ratings
    by_season = {}
    for m in rows:
        by_season.setdefault((m["competition_code"], m["season"]), []).append(m)
    notes = {}
    for ms in by_season.values():
        notes.update(pre_match_ratings(ms))

    def feats(m):
        rh, ra, _ = pre[m["match_id"]]
        nh, na = notes[m["match_id"]]
        return (rh - ra + home_adv) / 100, (nh - na) / 10

    def rated(m):
        return m["match_id"] in notes and pre[m["match_id"]][2] >= elo.BURN_IN

    variants = {"Note /100 seule": (1,), "Elo seul (site)": (0,), "Elo + note /100": (0, 1)}
    preds = {name: [] for name in [*variants, "Pinnacle clôture"]}
    for season in TEST:
        train = [m for m in rows if SEASONS[0] < m["season"] < season and rated(m)]
        ys = [2 - outcome(m) for m in train]              # 0 ext, 1 nul, 2 dom pour le logit
        coefs = {name: elo.fit_ordered_logit([tuple(feats(m)[i] for i in idx) for m in train], ys)
                 for name, idx in variants.items()}
        for m in rows:
            if m["season"] != season or not m["ps_close"] or not rated(m):
                continue
            f, y = feats(m), outcome(m)
            for name, idx in variants.items():
                c = coefs[name]
                eta = sum(b * f[i] for b, i in zip(c["betas"], idx))
                preds[name].append((list(elo.ordered_probs(eta, c)), y))
            preds["Pinnacle clôture"].append((book(m["ps_close"]), y))
    print(f"Note /100 — 8 championnats, saisons {TEST[0]} à {TEST[-1]}, matchs où les deux notes existent")
    for name, pairs in preds.items():
        print(f"  {name:24} {scores(pairs)}")


def backtest_ranking(rows, pre, home_adv):
    """Classement unifié : chaque méthode évaluée sur les mêmes matchs des 5 grands
    championnats (xG, notes /100 et cotes disponibles)."""
    from scoring import pre_match_ratings
    attach_xg(rows)
    xgf = elo.xg_form(rows)
    by_season = {}
    for m in rows:
        by_season.setdefault((m["competition_code"], m["season"]), []).append(m)
    notes = {}
    for ms in by_season.values():
        notes.update(pre_match_ratings(ms))

    def feats(m):
        rh, ra, _ = pre[m["match_id"]]
        nh, na = notes[m["match_id"]]
        return (rh - ra + home_adv) / 100, elo.xg_diff(*xgf["pre"][m["match_id"]]), (nh - na) / 10

    def usable(m):
        return (m["competition_code"] in US_LEAGUES and pre[m["match_id"]][2] >= elo.BURN_IN
                and elo.xg_diff(*xgf["pre"][m["match_id"]]) is not None and m["match_id"] in notes
                and m["b365"] and m["ps_close"])

    variants = {"Pronostic FootPulse (Elo + xG)": (0, 1), "Elo seul": (0,), "Note de forme /100": (2,)}
    preds = {name: [] for name in ["Fréquences", *variants, "Bet365 avant-match", "Pinnacle clôture"]}
    for season in TEST:
        train = [m for m in rows if SEASONS[0] < m["season"] < season and usable(m)]
        ys = [2 - outcome(m) for m in train]              # 0 ext, 1 nul, 2 dom pour le logit
        coefs = {name: elo.fit_ordered_logit([tuple(feats(m)[i] for i in idx) for m in train], ys)
                 for name, idx in variants.items()}
        base = [sum(outcome(m) == y for m in train) / len(train) for y in range(3)]
        for m in rows:
            if m["season"] != season or not usable(m):
                continue
            f, y = feats(m), outcome(m)
            preds["Fréquences"].append((base, y))
            for name, idx in variants.items():
                c = coefs[name]
                preds[name].append((list(elo.ordered_probs(sum(b * f[i] for b, i in zip(c["betas"], idx)), c)), y))
            preds["Bet365 avant-match"].append((book(m["b365"]), y))
            preds["Pinnacle clôture"].append((book(m["ps_close"]), y))

    def log_loss(pairs):
        return sum(-math.log(max(p[y], 1e-12)) for p, y in pairs) / len(pairs)
    low, high = log_loss(preds["Fréquences"]), log_loss(preds["Pinnacle clôture"])
    print(f"Classement — 5 grands championnats, saisons {TEST[0]} à {TEST[-1]}, mêmes matchs pour chaque méthode")
    for name, pairs in sorted(preds.items(), key=lambda kv: log_loss(kv[1])):
        print(f"  {name:32} indice {round((low - log_loss(pairs)) / (low - high) * 100):3d} · {scores(pairs)}")


if __name__ == "__main__":
    main()
