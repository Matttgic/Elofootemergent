"""Historique des cotes Pinnacle (football-data.co.uk) : construction du fichier utilisé
par la page « Cotes », test à l'aveugle de l'idée « parier d'après ce qui s'est passé
aux mêmes cotes », et recherche en ligne de commande.

    cd backend
    python -m tools.cotes_historiques --build          # télécharge et écrit data/cotes_pinnacle.csv.gz
    python -m tools.cotes_historiques                  # test à l'aveugle (hors ligne, sur le fichier)
    python -m tools.cotes_historiques --cotes 1.30 5.75 10.5 [--dom "Paris SG"] [--ext Marseille]

Le test prédit chaque saison (juillet à juin, de 2013-14 à 2025-26) avec les seules
saisons précédentes et compare aux cotes Pinnacle à la clôture :
  1. calibration : probabilité annoncée par la cote et fréquence réelle, par tranche ;
  2. cotes voisines (± 5 % sur chaque cote sans marge) : fréquences V/N/D des matchs
     passés, et paris quand elles disent que la cote est trop haute ;
  3. équipes : une équipe qui a battu ses cotes une saison le fait-elle encore la suivante ?
     Paris sur la victoire d'une équipe quand son historique à cote voisine est favorable ;
  4. zones de cotes rentables par le passé (ex. gros favoris), jouées la saison suivante ;
  5. combinaison des sources (poids réglés sur les saisons passées).
Les résultats de référence sont repris dans cotes_historiques.TEST_HISTORIQUE.
"""
import argparse
import collections
import csv
import gzip
import io
import itertools
import math
import os
import sys
import urllib.error
import urllib.request
from bisect import bisect_right
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cotes_historiques as ch  # noqa: E402

CACHE = Path(os.environ.get("BACKTEST_CACHE", Path.home() / ".cache" / "footpulse-backtest"))
MAIN = ["E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3", "D1", "D2", "I1", "I2",
        "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1"]
EXTRA = ["ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN", "MEX", "NOR", "POL", "ROU",
         "RUS", "SWE", "SWZ", "USA"]
PAYS = {"E": "Angleterre", "S": "Écosse", "D": "Allemagne", "I": "Italie", "F": "France",
        "N": "Pays-Bas", "B": "Belgique", "P": "Portugal", "T": "Turquie", "G": "Grèce"}
URL_MAIN = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
URL_EXTRA = "https://www.football-data.co.uk/new/{league}.csv"
FIRST_SEASON = 2012            # premières cotes Pinnacle chez football-data.co.uk


def _download(url, path):
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                path.write_bytes(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            path.write_bytes(b"")       # saison absente : on ne la redemande pas
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _odds(r):
    try:
        v = [float(r[c]) for c in ("PSCH", "PSCD", "PSCA")]
    except (KeyError, TypeError, ValueError):
        return None
    return v if all(x > 1 for x in v) else None


def _date(s):
    dd, mm, yy = s.split("/")
    return f"{'20' + yy if len(yy) == 2 else yy}-{mm}-{dd}"


def _country(league):
    return league if league in EXTRA else PAYS[league[0]]


def build():
    today = date.today()
    last = today.year if today.month >= 7 else today.year - 1
    rows = []
    for y in range(FIRST_SEASON, last + 1):
        season = f"{y % 100:02d}{(y + 1) % 100:02d}"
        for league in MAIN:
            text = _download(URL_MAIN.format(season=season, league=league), CACHE / f"{league}_{season}.csv")
            for r in csv.DictReader(io.StringIO(text)):
                o = _odds(r)
                if o and r.get("HomeTeam") and (r.get("FTHG") or "").isdigit() and (r.get("FTAG") or "").isdigit():
                    rows.append([league, _date(r["Date"]), r["HomeTeam"].strip(), r["AwayTeam"].strip(),
                                 int(r["FTHG"]), int(r["FTAG"]), *o])
    for league in EXTRA:
        text = _download(URL_EXTRA.format(league=league), CACHE / f"new_{league}.csv")
        for r in csv.DictReader(io.StringIO(text)):
            o = _odds(r)
            if o and r.get("Home") and (r.get("HG") or "").isdigit() and (r.get("AG") or "").isdigit():
                rows.append([league, _date(r["Date"]), r["Home"].strip(), r["Away"].strip(),
                             int(r["HG"]), int(r["AG"]), *o])
    # un même nom dans deux pays (ex. « Nacional ») : on précise le pays
    countries = collections.defaultdict(set)
    for r in rows:
        countries[r[2]].add(_country(r[0]))
        countries[r[3]].add(_country(r[0]))
    for r in rows:
        for j in (2, 3):
            if len(countries[r[j]]) > 1:
                r[j] = f"{r[j]} ({_country(r[0])})"
    rows.sort(key=lambda r: (r[1], r[0], r[2]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(ch.COLONNES)
    for r in rows:
        w.writerow(r[:6] + [f"{x:g}" for x in r[6:]])
    ch.DATA.parent.mkdir(parents=True, exist_ok=True)
    ch.DATA.write_bytes(gzip.compress(buf.getvalue().encode("utf-8"), compresslevel=9, mtime=0))
    homonymes = sorted(n for n, c in countries.items() if len(c) > 1)
    print(f"{len(rows)} matchs, {len({r[0] for r in rows})} championnats, du {rows[0][1]} au {rows[-1][1]} "
          f"-> {ch.DATA} ({ch.DATA.stat().st_size // 1024} Ko). Homonymes précisés : {', '.join(homonymes) or 'aucun'}")


# ---------------------------------------------------------------- test à l'aveugle

def _season(d):
    y, m = d // 10000, d // 100 % 100
    return y if m >= 7 else y - 1


def _label(y):
    return f"{y}-{(y + 1) % 100:02d}"


def _ll(p, y):
    return -math.log(max(p[y], 1e-9))


def _load():
    h = ch.historique()
    if h is None:
        sys.exit(f"{ch.DATA} absent : lancer d'abord --build")
    order = sorted(range(len(h)), key=lambda i: h.date[i])
    ms = [{"i": i, "season": _season(h.date[i]), "home": h.dom[i], "away": h.ext[i], "y": h.issue(i),
           "o": [h.cote(i, k) for k in range(3)], "f": [h.proba(i, k) for k in range(3)]} for i in order]
    return h, ms


def calibration_table(h):
    cal = ch.calibration(h)
    for name, rows in cal.items():
        print(f"\n  {name} : cote Pinnacle -> probabilité annoncée / fréquence réelle / rendement en pariant à chaque fois")
        for r in rows:
            hi = f"{r['cote_max']:.2f}" if r["cote_max"] else "+"
            print(f"    {r['cote_min']:5.2f}-{hi:<5} {r['matchs']:6d} matchs  {r['annonce_pct']:5.1f} % / "
                  f"{r['reel_pct']:5.1f} %  {r['roi_pct']:+6.1f} %")


class Grid:
    """Comptes V/N/D des matchs passés par case de 0,5 point de probabilité (domicile,
    extérieur), pour interroger vite les cotes voisines (± t sur chaque cote sans marge,
    la contrainte sur le nul, presque redondante, est ignorée ici)."""
    STEP = 200

    def __init__(self):
        self.c = collections.defaultdict(lambda: [0, 0, 0])

    def _k(self, p):
        return int(p * self.STEP)

    def add(self, m):
        self.c[(self._k(m["f"][0]), self._k(m["f"][2]))][m["y"]] += 1

    def query(self, f, t):
        out = [0, 0, 0]
        for a in range(self._k(f[0] / (1 + t)), self._k(f[0] / (1 - t)) + 1):
            for b in range(self._k(f[2] / (1 + t)), self._k(f[2] / (1 - t)) + 1):
                g = self.c.get((a, b))
                if g:
                    out[0] += g[0]
                    out[1] += g[1]
                    out[2] += g[2]
        return out


def run_test(precision=ch.PRECISION):
    h, ms = _load()
    t = precision / 100
    print(f"Historique : {len(h)} matchs Pinnacle (clôture), {len(h.ligues)} championnats, "
          f"{h.periode()[0]} au {h.periode()[1]}")
    print("\n1. Calibration des cotes (tout l'historique)")
    calibration_table(h)

    seasons = sorted({m["season"] for m in ms})
    first_test = seasons[2]
    grid = Grid()
    team_hist = collections.defaultdict(list)       # équipe -> [(proba victoire annoncée, gagné)]
    feats = []
    for s in seasons:
        test = [m for m in ms if m["season"] == s]
        if s >= first_test:
            for m in test:
                c = grid.query(m["f"], t)
                n = sum(c)
                m["sim"] = [x / n for x in c] if n >= ch.MIN_MATCHS else None
                m["team"] = []
                for side, k in (("home", 0), ("away", 2)):
                    past = [(p, w) for p, w in team_hist[m[side]] if abs(1 / p * m["f"][k] - 1) <= t]
                    nt = len(past)
                    m["team"].append((nt, sum(w for _, w in past), sum(p for p, _ in past)))
                feats.append(m)
        for m in test:
            grid.add(m)
            team_hist[m["home"]].append((m["f"][0], m["y"] == 0))
            team_hist[m["away"]].append((m["f"][2], m["y"] == 2))

    tested = [m for m in feats if m["sim"]]
    print(f"\n2. Cotes voisines (± {precision:g} %), saisons {_label(first_test)} à {_label(seasons[-1])}, "
          f"{len(tested)} matchs avec au moins {ch.MIN_MATCHS} matchs passés comparables")
    ll_p = sum(_ll(m["f"], m["y"]) for m in tested) / len(tested)
    ll_s = sum(_ll([max(x, 1e-3) for x in m["sim"]], m["y"]) for m in tested) / len(tested)
    print(f"  log-loss : cotes Pinnacle {ll_p:.4f} ; fréquences des matchs aux cotes voisines {ll_s:.4f}")
    bets = {}
    for thr in (0.0, 0.05):
        n = g = 0
        for m in tested:
            for k in range(3):
                if m["sim"][k] * m["o"][k] > 1 + thr:
                    n += 1
                    g += (m["o"][k] - 1) if m["y"] == k else -1
        bets[thr] = (n, 100 * g / max(n, 1))
        print(f"  parier quand fréquence passée × cote > {1 + thr:.2f} : {n} paris, rendement {bets[thr][1]:+.1f} %")
    n_all = 3 * len(tested)
    g_all = sum((m["o"][k] - 1) if m["y"] == k else -1 for m in tested for k in range(3))
    print(f"  (parier les trois issues de tous les matchs : rendement {100 * g_all / n_all:+.1f} %, la marge)")

    print("\n3. Équipes")
    res = collections.defaultdict(lambda: [0.0, 0])
    for m in ms:
        for side, k, win in (("home", 0, m["y"] == 0), ("away", 2, m["y"] == 2)):
            r = res[(m[side], m["season"])]
            r[0] += win - m["f"][k]
            r[1] += 1
    xs, ys = [], []
    for (team, s), (r, n) in res.items():
        nxt = res.get((team, s + 1))
        if n >= 20 and nxt and nxt[1] >= 20:
            xs.append(r / n)
            ys.append(nxt[0] / nxt[1])
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    corr = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)))
    print(f"  victoires au-dessus des cotes une saison -> la suivante : corrélation {corr:+.3f} ({len(xs)} équipes-saisons)")
    n = g = 0
    for m in feats:
        for j, k in ((0, 0), (1, 2)):
            nt, won, _ = m["team"][j]
            if nt >= 20 and won / nt * m["o"][k] > 1:
                n += 1
                g += (m["o"][k] - 1) if m["y"] == k else -1
    team_bets = (n, 100 * g / max(n, 1))
    print(f"  parier la victoire d'une équipe quand, à cote voisine, elle a gagné assez souvent par le passé "
          f"(≥ 20 matchs) : {n} paris, rendement {team_bets[1]:+.1f} %")

    print("\n4. Zones de cotes rentables par le passé (≥ 300 paris, rendement > 0), jouées la saison suivante")
    edges = ch.CAL_EDGES
    zone = collections.defaultdict(lambda: [0, 0.0])      # (issue, tranche) -> [paris, gain]
    n = g = 0
    per = []
    for s in seasons:
        test = [m for m in ms if m["season"] == s]
        if s >= first_test:
            ns = gs = 0
            for m in test:
                for k in range(3):
                    z = zone[(k, bisect_right(edges, m["o"][k]))]
                    if z[0] >= 300 and z[1] > 0:
                        ns += 1
                        gs += (m["o"][k] - 1) if m["y"] == k else -1
            n, g = n + ns, g + gs
            per.append(f"{_label(s)} {100 * gs / max(ns, 1):+.0f} %")
        for m in test:
            for k in range(3):
                z = zone[(k, bisect_right(edges, m["o"][k]))]
                z[0] += 1
                z[1] += (m["o"][k] - 1) if m["y"] == k else -1
    zones = (n, 100 * g / max(n, 1))
    print(f"  {n} paris, rendement {zones[1]:+.1f} % — par saison : {', '.join(per)}")

    print("\n5. Combinaison : cote + a × (cotes voisines − cote) + b × (surperformance passée des équipes)")

    def combo(m, a, b):
        f, sim = m["f"], m["sim"]
        p = [f[k] + a * (sim[k] - f[k]) for k in range(3)]
        for j, k in ((0, 0), (1, 2)):
            nt, won, ann = m["team"][j]
            p[k] += b * (won - ann) / (nt + 30)
        p = [max(x, 0.005) for x in p]
        s_ = sum(p)
        return [x / s_ for x in p]

    weights = list(itertools.product((0, 0.25, 0.5, 1.0), (0, 0.5, 1.0, 2.0)))
    ll_c = n_c = 0
    chosen = []
    for s in seasons:
        test = [m for m in tested if m["season"] == s]
        train = [m for m in tested if m["season"] < s]
        if not test or len(train) < 5000:
            continue
        a, b = min(weights, key=lambda w: sum(_ll(combo(m, *w), m["y"]) for m in train))
        chosen.append(f"{_label(s)} a={a:g} b={b:g}")
        ll_c += sum(_ll(combo(m, a, b), m["y"]) for m in test)
        n_c += len(test)
    ll_ref = sum(_ll(m["f"], m["y"]) for m in tested if m["season"] > seasons[2]) / n_c
    print(f"  poids retenus sur les saisons passées : {', '.join(chosen)}")
    print(f"  log-loss sur {n_c} matchs : cotes Pinnacle {ll_ref:.4f} ; combinaison {ll_c / n_c:.4f}")
    print("\nPour cotes_historiques.TEST_HISTORIQUE :")
    print({"matchs": len(tested), "saisons": f"{_label(first_test)} à {_label(seasons[-1])}",
           "logloss_pinnacle": round(ll_p, 4), "logloss_similaires": round(ll_s, 4),
           "paris_similaires": {"paris": bets[0.0][0], "roi_pct": round(bets[0.0][1], 1)},
           "paris_similaires_5": {"paris": bets[0.05][0], "roi_pct": round(bets[0.05][1], 1)},
           "marge_roi_pct": round(100 * g_all / n_all, 1),
           "correlation_equipes": round(corr, 3), "equipes_saisons": len(xs),
           "paris_equipes": {"paris": team_bets[0], "roi_pct": round(team_bets[1], 1)},
           "zones": {"paris": zones[0], "roi_pct": round(zones[1], 1)},
           "combinaison": {"matchs": n_c, "logloss": round(ll_c / n_c, 4), "logloss_pinnacle": round(ll_ref, 4)}})


def lookup(cotes, precision, dom, ext):
    h = ch.historique()
    r = ch.recherche(h, cotes, precision, dom, ext)
    s = r["similaires"]
    print(f"Cotes {cotes} : probabilités sans marge {r['probas_cotes']} (marge {r['marge_pct']} %)")
    print(f"{s['matchs']} matchs aux cotes voisines (± {precision:g} %), {s['identiques']} aux cotes identiques")
    for name, v in s["issues"].items():
        print(f"  {name:9} réel {v['reel_pct']} % (± {v['marge_erreur_pct']}) · annoncé {v['annonce_pct']} % · "
              f"rentable au-delà de {v['seuil_pct']} % · rendement à ta cote {v['rendement_pct']} %")
    for key in ("equipe_domicile", "equipe_exterieur"):
        e = r[key]
        if e and e["trouvee"]:
            print(f"{e['nom']} à cote de victoire voisine ({e['cote_min']}–{e['cote_max']}) : {e['matchs']} matchs, "
                  f"V {e['victoire_pct']} % / N {e['nul_pct']} % / D {e['defaite_pct']} % "
                  f"(annoncé {e['annonce_pct']} %, rendement historique {e['roi_historique_pct']} %)")
        elif e:
            print(f"{e['nom']} : équipe inconnue de l'historique")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="télécharger l'historique et écrire le fichier")
    ap.add_argument("--cotes", nargs=3, type=float, metavar=("DOM", "NUL", "EXT"))
    ap.add_argument("--dom")
    ap.add_argument("--ext")
    ap.add_argument("--precision", type=float, default=ch.PRECISION)
    args = ap.parse_args()
    if args.build:
        build()
    elif args.cotes:
        lookup(args.cotes, args.precision, args.dom, args.ext)
    else:
        run_test(args.precision)


if __name__ == "__main__":
    main()
