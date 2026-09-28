"""Simulation de paris : rapprochement cotes <-> matchs et calcul des mises.

Fonctions pures (sans base de données) afin d'être testables isolément.
"""
import difflib
import unicodedata
from datetime import datetime
from itertools import groupby

# Version du modèle de paris. Les paris figés avant la v2 (probabilités gonflées
# par la calibration non chronologique, appariement cotes/matchs trop permissif)
# sont exclus du bilan et remplacés s'ils sont encore à venir.
MODELE_PARIS = 2

BANKROLL = 100.0
KELLY_FRACTION = 0.25     # quart de Kelly
KELLY_CAP = 0.05          # mise maximale : 5 % de la bankroll courante par pari
MATCH_WINDOW_H = 36       # écart max (h) entre le coup d'envoi des cotes et celui du match
MIN_TEAM_SIM = 0.6        # similarité minimale de chaque nom d'équipe


def _tn(name):
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    drop = {"fc", "cf", "ac", "sc", "as", "rc", "sv", "cd", "ud", "afc", "1", "calcio",
            "club", "de", "sad", "ss", "us", "bk", "if", "sk", "the"}
    toks = [t for t in "".join(c if c.isalnum() else " " for c in s).split() if t not in drop]
    return " ".join(toks)


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
    a = _tn(odds_name)
    return max(_name_sim(a, _tn(fd_team.get(k))) for k in ("name", "shortName"))


def _parse(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


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
