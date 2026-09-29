"""Backtest du modèle Elo sur l'historique football-data.co.uk (résultats + cotes).

Télécharge (une fois, dans un cache local) les saisons 2019-20 à aujourd'hui de 8
championnats européens, puis compare, saison par saison et sans regarder l'avenir
(coefficients 1N2 ajustés sur les seules saisons précédentes) :
  - les probabilités 1N2 du modèle Elo du site ;
  - de simples fréquences domicile / nul / extérieur (référence naïve) ;
  - les cotes des bookmakers (Bet365 avant-match, moyenne et Pinnacle à la clôture) ;
et simule des stratégies de paris aux cotes Bet365.

    cd backend && python -m tools.backtest_historique [--k 20] [--home-adv 60]

Réseau requis ; ne tourne pas dans la CI. Résultats de référence (septembre 2026,
13 273 matchs de 2021-22 à 2026-27) : log-loss Elo 0,990 ; fréquences 1,073 ;
Bet365 0,971 ; Pinnacle clôture 0,967. Aucune stratégie n'est rentable face aux
cotes réelles (favori du modèle −4,6 %, « value » de −8,8 % à −13,9 %).
"""
import argparse
import csv
import io
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
    args = ap.parse_args()

    rows = load()
    pre = elo.run_elo(rows, k=args.k, home_adv=args.home_adv)["pre"]
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


if __name__ == "__main__":
    main()
