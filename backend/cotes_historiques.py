"""Cotes similaires : ce qui s'est passé, par le passé, dans les matchs dont les cotes
Pinnacle à la clôture étaient proches de celles d'un match donné, et dans les matchs
où une équipe avait une cote de victoire proche.

Historique : football-data.co.uk, 38 championnats, de 2012 à début 2026, figé dans
data/cotes_pinnacle.csv.gz (le site ne publie plus les cotes Pinnacle depuis) et
reconstruit par `python -m tools.cotes_historiques --build`.

Les cotes sont d'abord converties en probabilités sans la marge du bookmaker (1/cote,
ramenées à 100 %), ce qui permet aussi de comparer les cotes d'un autre bookmaker à
l'historique Pinnacle. Deux matchs ont des « cotes similaires » quand chacune des trois
cotes sans marge diffère de moins de `precision` % ; pour une équipe, seule sa cote de
victoire compte. Un même triplet de cotes se répète rarement (75 % des matchs n'ont
aucun jumeau exact, jamais plus de 10), d'où cette tolérance.
"""
import csv
import gzip
import math
from array import array
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "cotes_pinnacle.csv.gz"

LIGUES = {
    "E0": "Premier League", "E1": "Championship", "E2": "League One", "E3": "League Two",
    "EC": "National League", "SC0": "Premiership (Écosse)", "SC1": "Championship (Écosse)",
    "SC2": "League One (Écosse)", "SC3": "League Two (Écosse)", "D1": "Bundesliga", "D2": "2. Bundesliga",
    "I1": "Serie A", "I2": "Serie B", "SP1": "Liga", "SP2": "Liga 2 (Espagne)", "F1": "Ligue 1",
    "F2": "Ligue 2", "N1": "Eredivisie", "B1": "Pro League (Belgique)", "P1": "Liga Portugal",
    "T1": "Süper Lig", "G1": "Super League (Grèce)", "BRA": "Brasileirão", "ARG": "Liga Profesional (Argentine)",
    "USA": "MLS", "JPN": "J1 League", "MEX": "Liga MX", "AUT": "Bundesliga (Autriche)",
    "SWZ": "Super League (Suisse)", "DNK": "Superliga (Danemark)", "NOR": "Eliteserien",
    "SWE": "Allsvenskan", "POL": "Ekstraklasa", "ROU": "Liga I (Roumanie)",
    "RUS": "Premier League (Russie)", "IRL": "Premier Division (Irlande)", "FIN": "Veikkausliiga",
    "CHN": "Super League (Chine)",
}

PRECISION = 5.0           # tolérance par défaut (%) sur chaque cote sans marge
MIN_MATCHS = 30           # en dessous, l'échantillon est signalé comme trop petit
EXEMPLES = 10
SCORES = 8                # scores exacts les plus fréquents affichés
ISSUES = ("domicile", "nul", "exterieur")
CAL_EDGES = [1.0, 1.15, 1.25, 1.35, 1.5, 1.7, 1.9, 2.1, 2.4, 2.8, 3.3, 4, 5, 7, 10, 15, 1000]
CAL_MIN = 200

# Test à l'aveugle (python -m tools.cotes_historiques) : chaque saison prédite avec les
# seules saisons précédentes, cotes Pinnacle à la clôture. Repris sur la page « Cotes ».
TEST_HISTORIQUE = {
    "matchs": 148_353, "saisons": "2013-14 à 2025-26",
    "logloss_pinnacle": 1.0019, "logloss_similaires": 1.0030,
    "paris_similaires": {"paris": 90_364, "roi_pct": -3.8},     # fréquence passée × cote > 1
    "paris_similaires_5": {"paris": 21_639, "roi_pct": -7.0},   # ... > 1,05
    "marge_roi_pct": -4.0,                                      # parier toutes les issues
    "correlation_equipes": 0.009, "equipes_saisons": 6_967,
    "paris_equipes": {"paris": 41_604, "roi_pct": -2.4},
    "zones": {"paris": 43_056, "roi_pct": -1.8},
    "combinaison": {"matchs": 136_988, "logloss": 1.0013, "logloss_pinnacle": 1.0013, "poids": 0},
    # tendance générale de la page (cotes voisines + équipes mis ensemble)
    "tendance": {"matchs": 148_353, "logloss": 1.0030, "logloss_pinnacle": 1.0019,
                 "reussite_pct": 50.3, "reussite_cote_pct": 50.3, "paris": 90_289, "roi_pct": -3.8},
}


def fair_probs(cotes):
    """Probabilités sans la marge du bookmaker, et la marge (en fraction)."""
    inv = [1 / c for c in cotes]
    s = sum(inv)
    return [x / s for x in inv], s - 1


def _cell(p):
    return min(int(p * 100), 99)


class Historique:
    """Historique en colonnes (quelques Mo en mémoire pour ~160 000 matchs), trié par
    probabilités (domicile, extérieur) pour trouver vite les cotes voisines."""

    def __init__(self, rows):
        """`rows` : itérable de (ligue, date AAAAMMJJ, domicile, extérieur, buts dom,
        buts ext, (cotes dom, nul, ext))."""
        self.ligues, self.equipes = [], []
        lig, self.index_equipe = {}, {}
        ligue, dates, dom, ext = array("B"), array("I"), array("H"), array("H")
        buts, cotes, probas = array("B"), array("f"), array("f")

        def ident(table, names, name):
            if name not in table:
                table[name] = len(names)
                names.append(name)
            return table[name]

        for lg, d, home, away, bh, ba, odds in rows:
            ligue.append(ident(lig, self.ligues, lg))
            dates.append(d)
            dom.append(ident(self.index_equipe, self.equipes, home))
            ext.append(ident(self.index_equipe, self.equipes, away))
            buts.extend((min(bh, 255), min(ba, 255)))
            cotes.extend(odds)
            probas.extend(fair_probs(odds)[0])
        n = len(dates)
        keys = [(_cell(probas[3 * i]) * 100 + _cell(probas[3 * i + 2])) * 10**8 + dates[i] for i in range(n)]
        order = sorted(range(n), key=keys.__getitem__)
        del keys
        self.ligue = array("B", (ligue[i] for i in order))
        self.date = array("I", (dates[i] for i in order))
        self.dom = array("H", (dom[i] for i in order))
        self.ext = array("H", (ext[i] for i in order))
        self.buts = array("B", (buts[2 * i + j] for i in order for j in (0, 1)))
        self.cotes = array("f", (cotes[3 * i + k] for i in order for k in range(3)))
        self.probas = array("f", (probas[3 * i + k] for i in order for k in range(3)))
        del order, ligue, dates, dom, ext, buts, cotes, probas
        self.blocs = {}        # (case domicile, case extérieur) -> (début, fin)
        self.par_equipe = {}
        self.equipe_ligues = {}
        for i in range(n):
            key = (_cell(self.probas[3 * i]), _cell(self.probas[3 * i + 2]))
            start, _ = self.blocs.get(key, (i, i))
            self.blocs[key] = (start, i + 1)
            for t in (self.dom[i], self.ext[i]):
                self.par_equipe.setdefault(t, array("I")).append(i)
                self.equipe_ligues.setdefault(t, set()).add(self.ligue[i])

    def __len__(self):
        return len(self.date)

    def issue(self, i):
        h, a = self.buts[2 * i], self.buts[2 * i + 1]
        return 0 if h > a else (1 if h == a else 2)

    def cote(self, i, k):
        return self.cotes[3 * i + k]

    def proba(self, i, k):
        return self.probas[3 * i + k]

    def periode(self):
        return _date(min(self.date)), _date(max(self.date))


def _date(d):
    return f"{d // 10000:04d}-{d // 100 % 100:02d}-{d % 100:02d}"


COLONNES = ["ligue", "date", "domicile", "exterieur", "buts_dom", "buts_ext", "cote_dom", "cote_nul", "cote_ext"]


def parse_rows(lines):
    """Lignes CSV du fichier (en-tête compris) -> tuples attendus par Historique."""
    reader = csv.reader(lines)
    head = next(reader)
    if head != COLONNES:
        raise ValueError(f"colonnes inattendues : {head}")
    for lg, d, home, away, bh, ba, co_h, co_d, co_a in reader:
        yield lg, int(d.replace("-", "")), home, away, int(bh), int(ba), (float(co_h), float(co_d), float(co_a))


@lru_cache(maxsize=1)
def historique(path=DATA):
    """Historique chargé une fois (None si le fichier est absent)."""
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            return Historique(parse_rows(f))
    except FileNotFoundError:
        return None


def _ci(k, n):
    """Demi-largeur de l'intervalle de confiance à 95 % d'une fréquence (en points)."""
    if not n:
        return None
    p = k / n
    return round(196 * math.sqrt(p * (1 - p) / n), 1)


def _scores(scores, n):
    """Scores exacts les plus fréquents : [{"score": "1-0", "matchs": 12, "pct": 9.5}]."""
    c = {}
    for sc in scores:
        c[sc] = c.get(sc, 0) + 1
    top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:SCORES]
    return [{"score": f"{a}-{b}", "matchs": k, "pct": round(100 * k / n, 1)} for (a, b), k in top]


def _score(h, i, inverse=False):
    a, b = h.buts[2 * i], h.buts[2 * i + 1]
    return (b, a) if inverse else (a, b)


def _exemple(h, i, equipe=None):
    d, e = h.equipes[h.dom[i]], h.equipes[h.ext[i]]
    out = {"date": _date(h.date[i]), "ligue": LIGUES.get(h.ligues[h.ligue[i]], h.ligues[h.ligue[i]]),
           "domicile": d, "exterieur": e, "score": f"{h.buts[2 * i]}-{h.buts[2 * i + 1]}",
           "cotes": [round(h.cote(i, k), 2) for k in range(3)]}
    if equipe is not None:
        out["terrain"] = "domicile" if h.dom[i] == equipe else "exterieur"
    return out


def voisins(h, cotes, precision=PRECISION):
    """Index des matchs dont les trois cotes sans marge sont à ± precision % des cotes."""
    q, _ = fair_probs(cotes)
    t = precision / 100
    lo = [x / (1 + t) for x in q]
    hi = [x / (1 - t) for x in q]
    found = []
    for ch in range(_cell(lo[0]), _cell(hi[0]) + 1):
        for ca in range(_cell(lo[2]), _cell(hi[2]) + 1):
            bloc = h.blocs.get((ch, ca))
            if not bloc:
                continue
            for i in range(*bloc):
                if all(lo[k] <= h.proba(i, k) <= hi[k] for k in range(3)):
                    found.append(i)
    return found


def similaires(h, cotes, precision=PRECISION, found=None):
    """Matchs dont les trois cotes sans marge sont à ± precision % de celles demandées."""
    if found is None:
        found = voisins(h, cotes, precision)
    n = len(found)
    count = [0, 0, 0]
    gain = [0.0, 0.0, 0.0]
    annonce = [0.0, 0.0, 0.0]
    somme_cotes = [0.0, 0.0, 0.0]
    for i in found:
        y = h.issue(i)
        count[y] += 1
        for k in range(3):
            annonce[k] += h.proba(i, k)
            somme_cotes[k] += h.cote(i, k)
            gain[k] += (h.cote(i, k) - 1) if y == k else -1
    exact = sum(1 for i in found if all(abs(h.cote(i, k) - cotes[k]) < 0.005 for k in range(3)))
    issues = {}
    for k, name in enumerate(ISSUES):
        reel = count[k] / n if n else None
        issues[name] = {
            "matchs": count[k],
            "reel_pct": round(100 * reel, 1) if n else None,
            "marge_erreur_pct": _ci(count[k], n),
            "annonce_pct": round(100 * annonce[k] / n, 1) if n else None,
            "seuil_pct": round(100 / cotes[k], 1),
            "rendement_pct": round(100 * (reel * cotes[k] - 1), 1) if n else None,
            "roi_historique_pct": round(100 * gain[k] / n, 1) if n else None,
        }
    recent = sorted(found, key=lambda i: h.date[i], reverse=True)[:EXEMPLES]
    # cotes Pinnacle moyennes des matchs trouvés : l'équivalent, marge Pinnacle comprise,
    # des cotes demandées (plus basses chez un bookmaker qui prend plus de marge)
    return {"precision_pct": precision, "matchs": n, "identiques": exact,
            "cotes_pinnacle": [round(x / n, 2) for x in somme_cotes] if n else None,
            "suffisant": n >= MIN_MATCHS, "issues": issues,
            "scores": _scores((_score(h, i) for i in found), n),
            "exemples": [_exemple(h, i) for i in recent]}


def trouver_equipe(h, nom):
    """Index de l'équipe (nom exact, sinon sans tenir compte de la casse), ou None."""
    if not nom:
        return None
    if nom in h.index_equipe:
        return h.index_equipe[nom]
    low = nom.strip().lower()
    return next((i for n, i in h.index_equipe.items() if n.lower() == low), None)


def _resultat_equipe(h, equipe, i):
    """0 victoire, 1 nul, 2 défaite de l'équipe dans le match i."""
    k = 0 if h.dom[i] == equipe else 2
    y = h.issue(i)
    return 0 if y == k else (1 if y == 1 else 2)


def matchs_equipe(h, equipe, cote, precision=PRECISION, cote_adverse=None, cote_nul=None):
    """Index des matchs de l'équipe où sa cote de victoire (sans marge) était à
    ± precision % de celle demandée, quel que soit le terrain."""
    if cote_adverse and cote_nul:
        q, _ = fair_probs((cote, cote_nul, cote_adverse))
        target = q[0]
    else:
        target = 1 / cote
    t = precision / 100
    lo, hi = target / (1 + t), target / (1 - t)
    return [i for i in h.par_equipe.get(equipe, ())
            if lo <= h.proba(i, 0 if h.dom[i] == equipe else 2) <= hi]


def equipe_a_cote(h, equipe, cote, precision=PRECISION, cote_adverse=None, cote_nul=None, found=None):
    """Matchs de l'équipe où sa cote de victoire (sans marge) était à ± precision % de
    celle demandée, quel que soit le terrain : victoires, nuls, défaites."""
    if found is None:
        found = matchs_equipe(h, equipe, cote, precision, cote_adverse, cote_nul)
    n = len(found)
    res = [0, 0, 0]       # victoire, nul, défaite
    gain = annonce = 0.0
    cotes = []
    for i in found:
        k = 0 if h.dom[i] == equipe else 2
        r = _resultat_equipe(h, equipe, i)
        res[r] += 1
        annonce += h.proba(i, k)
        gain += (h.cote(i, k) - 1) if r == 0 else -1
        cotes.append(h.cote(i, k))
    recent = sorted(found, key=lambda i: h.date[i], reverse=True)[:EXEMPLES]
    pct = (lambda x: round(100 * x / n, 1)) if n else (lambda x: None)
    return {
        "nom": h.equipes[equipe], "trouvee": True, "precision_pct": precision, "matchs": n,
        "suffisant": n >= MIN_MATCHS,
        "ligues": sorted(LIGUES.get(h.ligues[li], h.ligues[li]) for li in h.equipe_ligues.get(equipe, ())),
        "cote_min": round(min(cotes), 2) if cotes else None, "cote_max": round(max(cotes), 2) if cotes else None,
        "domicile": sum(1 for i in found if h.dom[i] == equipe),
        "victoires": res[0], "nuls": res[1], "defaites": res[2],
        "victoire_pct": pct(res[0]), "nul_pct": pct(res[1]), "defaite_pct": pct(res[2]),
        "marge_erreur_pct": _ci(res[0], n),
        "annonce_pct": pct(annonce), "seuil_pct": round(100 / cote, 1),
        "rendement_pct": round(100 * (res[0] / n * cote - 1), 1) if n else None,
        "roi_historique_pct": pct(gain),
        "exemples": [_exemple(h, i, equipe) for i in recent],
    }


def tendance(h, found, equipes):
    """Tous les matchs mis ensemble, chacun compté une fois, vus depuis le match demandé :
    ceux aux cotes voisines, plus ceux de chaque équipe à sa cote de victoire (sa victoire
    compte pour l'issue de son côté, sa défaite pour l'autre). `equipes` : liste de
    (index de l'équipe, 0 si elle reçoit / 2 si elle se déplace, ses matchs trouvés)."""
    issue_de = {i: (h.issue(i), _score(h, i)) for i in found}
    for equipe, cote_k, matchs in equipes:
        for i in matchs:
            r = _resultat_equipe(h, equipe, i)
            # score retourné si l'équipe jouait de l'autre côté qu'ici
            inverse = (h.dom[i] == equipe) != (cote_k == 0)
            issue_de.setdefault(i, (cote_k if r == 0 else (1 if r == 1 else 2 - cote_k), _score(h, i, inverse)))
    n = len(issue_de)
    count = [0, 0, 0]
    for y, _ in issue_de.values():
        count[y] += 1
    out = {"matchs": n}
    for k, name in enumerate(ISSUES):
        out[name] = count[k]
        out[f"{name}_pct"] = round(100 * count[k] / n, 1) if n else None
    out["issue"] = ISSUES[max(range(3), key=count.__getitem__)] if n else None
    out["scores"] = _scores((sc for _, sc in issue_de.values()), n) if n else []
    return out


def recherche(h, cotes, precision=PRECISION, equipe_domicile=None, equipe_exterieur=None):
    """Réponse complète : probabilités des cotes, matchs similaires, historique des équipes
    et, si une équipe est connue, la tendance de tous ces matchs mis ensemble."""
    q, marge = fair_probs(cotes)
    found = voisins(h, cotes, precision)
    out = {
        "cotes": dict(zip(ISSUES, cotes)),
        "marge_pct": round(100 * marge, 1),
        "probas_cotes": {name: round(100 * q[k], 1) for k, name in enumerate(ISSUES)},
        "similaires": similaires(h, cotes, precision, found),
        "equipe_domicile": None, "equipe_exterieur": None, "tendance": None,
    }
    equipes = []
    for key, nom, k in (("equipe_domicile", equipe_domicile, 0), ("equipe_exterieur", equipe_exterieur, 2)):
        if not nom:
            continue
        idx = trouver_equipe(h, nom)
        if idx is None:
            out[key] = {"nom": nom, "trouvee": False}
            continue
        matchs = matchs_equipe(h, idx, cotes[k], precision, cote_adverse=cotes[2 - k], cote_nul=cotes[1])
        out[key] = equipe_a_cote(h, idx, cotes[k], precision, found=matchs)
        equipes.append((idx, k, matchs))
    if any(m for _, _, m in equipes):
        out["tendance"] = tendance(h, found, equipes)
    return out


def liste_equipes(h):
    """Équipes de l'historique, par ordre alphabétique, avec leurs championnats."""
    return sorted(({"nom": n, "matchs": len(h.par_equipe.get(i, ())),
                    "ligues": sorted(LIGUES.get(h.ligues[li], h.ligues[li]) for li in h.equipe_ligues.get(i, ()))}
                   for i, n in enumerate(h.equipes)), key=lambda e: e["nom"].lower())


def calibration(h):
    """Par issue et par tranche de cote : probabilité annoncée par Pinnacle, fréquence
    réelle et rendement si l'on avait parié cette issue à chaque fois."""
    acc = {}
    for i in range(len(h)):
        y = h.issue(i)
        for k in range(3):
            c = h.cote(i, k)
            b = min(bisect_right(CAL_EDGES, c) - 1, len(CAL_EDGES) - 2)
            a = acc.setdefault((k, b), [0, 0, 0.0, 0.0])
            a[0] += 1
            a[1] += y == k
            a[2] += h.proba(i, k)
            a[3] += (c - 1) if y == k else -1
    out = {}
    for k, name in enumerate(ISSUES):
        rows = []
        for b in range(len(CAL_EDGES) - 1):
            n, won, ann, gain = acc.get((k, b), (0, 0, 0.0, 0.0))
            if n < CAL_MIN:
                continue
            rows.append({"cote_min": CAL_EDGES[b], "cote_max": CAL_EDGES[b + 1] if b < len(CAL_EDGES) - 2 else None,
                         "matchs": n, "annonce_pct": round(100 * ann / n, 1), "reel_pct": round(100 * won / n, 1),
                         "roi_pct": round(100 * gain / n, 1)})
        out[name] = rows
    return out


def resume(h):
    debut, fin = h.periode()
    return {"matchs": len(h), "championnats": len(h.ligues), "equipes": len(h.equipes),
            "debut": debut, "fin": fin, "source": "football-data.co.uk — cotes Pinnacle à la clôture"}
