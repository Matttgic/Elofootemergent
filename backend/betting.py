"""Simulation de paris : rapprochement cotes <-> matchs et calcul des mises.

Fonctions pures (sans base de données) afin d'être testables isolément.
"""
import difflib
from datetime import datetime, timezone
from itertools import groupby

from teamnames import normalize_team_name

# Version du modèle de paris. v2 : calibration chronologique et appariement strict ;
# v3 : probabilités du modèle Elo. Les paris figés avec une version antérieure sont
# exclus du bilan et remplacés s'ils sont encore à venir.
MODELE_PARIS = 3

VALUE_EDGE = 0.05         # avantage minimal (espérance de gain) pour signaler une « value »

BANKROLL = 100.0
KELLY_FRACTION = 0.25     # quart de Kelly
KELLY_CAP = 0.05          # mise maximale : 5 % de la bankroll courante par pari
MATCH_WINDOW_H = 36       # écart max (h) entre le coup d'envoi des cotes et celui du match
MIN_TEAM_SIM = 0.6        # similarité minimale de chaque nom d'équipe
VOID_AFTER_H = 72         # match non joué dans ce délai après l'horaire prévu => pari annulé


# Noms The Odds API trop éloignés de football-data pour la similarité seule
ODDS_ALIASES = {
    "Rennes": "Stade Rennais",   # « rennes » ressemble plus à « nantes » qu'à « stade rennais »
    "Inter Milan": "Inter",      # sinon ex æquo avec l'AC Milan (« milan » ⊂ « inter milan »)
}


def _name_sim(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:   # « inter » ⊂ « inter milan », « bayern » ⊂ « bayern munich »
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def team_similarity(odds_name, fd_team):
    """Similarité (0-1) entre un nom The Odds API et une équipe football-data."""
    a = normalize_team_name(ODDS_ALIASES.get(odds_name, odds_name))
    return max(_name_sim(a, normalize_team_name(fd_team.get(k))) for k in ("name", "shortName"))


def _parse(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def match_fixture(fx, matches, window_h=MATCH_WINDOW_H, min_sim=MIN_TEAM_SIM):
    """Match football-data correspondant à une rencontre The Odds API, ou None.

    Seuls les matchs dont le coup d'envoi est proche (± window_h heures) sont
    candidats ; on retient la meilleure similarité cumulée domicile + extérieur,
    chaque équipe devant atteindre `min_sim`.
    """
    kick = _parse(fx.get("commence_time"))
    if kick is None:
        return None
    best, best_score = None, 0.0
    for m in matches:
        mk = _parse(m.get("utc_date"))
        if mk is None or abs((mk - kick).total_seconds()) > window_h * 3600:
            continue
        sh = team_similarity(fx.get("home_team"), m.get("home_team") or {})
        sa = team_similarity(fx.get("away_team"), m.get("away_team") or {})
        if sh >= min_sim and sa >= min_sim and sh + sa > best_score:
            best, best_score = m, sh + sa
    return best


def settle_outcome(bet, match, now):
    """Issue d'un pari en attente : 'won', 'lost', 'void' (mise remboursée) ou None
    (toujours en attente). Comme chez les bookmakers, un match annulé, attribué sur
    tapis vert, ou non joué dans les VOID_AFTER_H heures suivant l'horaire prévu au
    moment du pari (report, suspension) est annulé."""
    match = match or {}
    kick = _parse(bet.get("commence_time"))
    late = VOID_AFTER_H * 3600
    if match.get("status") == "CANCELLED":
        return "void"
    ft = (match.get("score") or {}).get("fullTime") or {}
    h, a = ft.get("home"), ft.get("away")
    if match.get("status") == "FINISHED" and h is not None and a is not None:
        played = _parse(match.get("utc_date"))
        if kick and played and (played - kick).total_seconds() > late:
            return "void"   # reporté puis joué hors délai
        result = "home" if h > a else ("away" if a > h else "draw")
        return "won" if result == bet.get("fav_side") else "lost"
    if kick and (now - kick).total_seconds() > late:
        return "void"
    return None


OUTCOMES = (("domicile", "home_odds", "domicile_pct"), ("nul", "draw_odds", "nul_pct"),
            ("exterieur", "away_odds", "exterieur_pct"))


def odds_view(bet):
    """Cotes 1N2 figées pour un match (None sans cotes)."""
    if not bet or not (bet.get("home_odds") and bet.get("away_odds")):
        return None
    return {"domicile": bet.get("home_odds"), "nul": bet.get("draw_odds"),
            "exterieur": bet.get("away_odds"), "bookmaker": bet.get("bookmaker")}


def value_pick(pred, bet, edge=VALUE_EDGE):
    """Issue dont l'espérance de gain p × cote − 1 est la plus forte, si elle atteint
    `edge` ; None sinon. Signal statistique, pas une garantie : sur l'historique, ces
    écarts entre modèle et bookmaker n'ont pas été rentables (voir Méthodologie)."""
    if not pred or not bet:
        return None
    best = None
    for issue, odds_key, pct_key in OUTCOMES:
        odds, p = bet.get(odds_key), (pred.get(pct_key) or 0) / 100
        if odds and odds > 1:
            ev = p * odds - 1
            if best is None or ev > best["ev"]:
                best = {"issue": issue, "cote": odds, "proba_pct": round(p * 100, 1), "ev": ev}
    if not best or best["ev"] < edge:
        return None
    return {"issue": best["issue"], "cote": best["cote"], "proba_pct": best["proba_pct"],
            "avantage_pct": round(best["ev"] * 100, 1)}


ISSUE_RESULT = {"domicile": "home", "nul": "draw", "exterieur": "away"}


def clv_pct(bet_odds, closing_odds):
    """Valeur de clôture : cote obtenue / dernière cote relevée avant le match − 1.
    Positive = pari pris à meilleur prix que le marché final (bon signe à long terme)."""
    if not bet_odds or not closing_odds or closing_odds <= 1:
        return None
    return round((bet_odds / closing_odds - 1) * 100, 2)


def value_bets(bets):
    """Paris de la stratégie « Value » : l'issue repérée à la prise du pari (avantage
    ≥ VALUE_EDGE), réglée d'après le résultat du match. Même format que les paris
    « favori » pour simulate()."""
    out = []
    for b in bets:
        v = b.get("value")
        if not v or b.get("status") not in ("won", "lost"):
            continue
        won = b.get("resultat") == ISSUE_RESULT[v["issue"]]
        out.append({"status": "won" if won else "lost", "fav_odds": v["cote"],
                    "model_prob": v["proba_pct"] / 100, "commence_time": b.get("commence_time"),
                    "tranche": b.get("tranche")})
    return out


def kelly_fraction(p, odds):
    """Part de bankroll misée : quart de Kelly plafonné à KELLY_CAP (0 sans avantage)."""
    b = (odds or 0) - 1
    if p is None or b <= 0:
        return 0.0
    full = (b * p - (1 - p)) / b
    return max(0.0, min(KELLY_CAP, KELLY_FRACTION * full))


def simulate(bets):
    """Bilan d'une liste de paris réglés : mise fixe (1 u/pari) et Kelly fractionné
    composé (bankroll initiale 100 u, gains réinvestis). Les paris d'un même coup
    d'envoi sont misés sur la même bankroll, sans jamais engager plus qu'elle."""
    n = len(bets)
    wins = sum(1 for b in bets if b["status"] == "won")
    pnl_f = sum((b["fav_odds"] - 1) if b["status"] == "won" else -1 for b in bets)

    bankroll, staked = BANKROLL, 0.0
    ordered = sorted(bets, key=lambda b: b.get("commence_time") or "")
    for _, group in groupby(ordered, key=lambda b: b.get("commence_time") or ""):
        group = list(group)
        fracs = [kelly_fraction(b.get("model_prob"), b["fav_odds"]) for b in group]
        scale = max(1.0, sum(fracs))
        start = bankroll
        for b, f in zip(group, fracs):
            stake = start * f / scale
            staked += stake
            bankroll += stake * (b["fav_odds"] - 1) if b["status"] == "won" else -stake
    pnl_k = bankroll - BANKROLL

    return {
        "paris": n, "gagnes": wins,
        "taux_reussite": round(wins / n * 100, 1) if n else 0,
        "mise_fixe": {"mise_totale": round(n * 1.0, 2), "gain_net": round(pnl_f, 2),
                      "roi": round(pnl_f / n * 100, 1) if n else 0, "bankroll": round(BANKROLL + pnl_f, 2)},
        "kelly": {"mise_totale": round(staked, 2), "gain_net": round(pnl_k, 2),
                  "roi": round(pnl_k / staked * 100, 1) if staked > 0 else 0,
                  "bankroll": round(bankroll, 2)},
    }
