"""Classement Elo des équipes et probabilités victoire / nul / défaite.

Elo « football » : après chaque match, le vainqueur prend des points au perdant,
d'autant plus que le résultat était inattendu et l'écart de buts large. L'équipe
à domicile reçoit un bonus fixe (avantage du terrain) dans le calcul de l'attendu.
Les notes traversent les saisons ; une équipe qui apparaît dans un championnat
déjà noté (promue) démarre au niveau de ses équipes les plus faibles. Les coupes
européennes relient les championnats entre eux (mêmes identifiants d'équipes).

Probabilités 1N2 : modèle logistique ordonné (issue défaite < nul < victoire du
point de vue domicile) ajusté par maximum de vraisemblance sur les matchs passés,
en fonction de l'écart Elo avant-match (avantage du terrain compris).

Fonctions pures, sans base de données : testables et réutilisées par le backtest.
Paramètres réglés sur 8 saisons de 8 championnats européens (football-data.co.uk,
voir tools/backtest_historique.py) : K = 20 et aucune régression à l'intersaison
donnent la meilleure log-loss ; l'avantage du terrain (50 à 80 points) change peu
le résultat car le modèle 1N2 réajuste ses seuils.
"""
import math

BASE = 1500.0
K = 20.0                 # vitesse d'ajustement par match
HOME_ADV = 60.0          # avantage du terrain, en points Elo
NEWCOMER_PCTL = 0.20     # une équipe promue démarre à ce quantile de son championnat
MIN_TEAMS_FOR_PCTL = 8

# Coefficients 1N2 par défaut (ajustés sur 17 000 matchs historiques) si l'échantillon
# disponible est trop petit pour les réajuster
DEFAULT_LOGIT = {"beta": 0.50, "theta_away": -0.575, "theta_draw": 0.62}
MIN_FIT_MATCHES = 300
BURN_IN = 10             # matchs joués par chaque équipe avant d'entrer dans l'ajustement


def _finished(m):
    ft = (m.get("score") or {}).get("fullTime") or {}
    return (m.get("status") == "FINISHED" and m.get("utc_date")
            and (m.get("home_team") or {}).get("id") is not None
            and (m.get("away_team") or {}).get("id") is not None
            and ft.get("home") is not None and ft.get("away") is not None)


def margin_multiplier(goal_diff):
    """Poids de l'écart de buts (barème World Football Elo)."""
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8


def expected_home(elo_home, elo_away, home_adv=HOME_ADV):
    """Score attendu de l'équipe à domicile (victoire = 1, nul = 0,5)."""
    return 1 / (1 + 10 ** (-(elo_home + home_adv - elo_away) / 400))


def _quantile(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def run_elo(matches, cups=(), k=K, home_adv=HOME_ADV):
    """Parcourt les matchs terminés dans l'ordre chronologique.

    `cups` : codes des compétitions à élimination / sans championnat (l'équipe y garde
    son championnat d'origine). Retourne un dict :
      ratings  {team_id: elo actuel}
      pre      {match_id: (elo_dom, elo_ext, nb_matchs_min)} notes AVANT chaque match
      history  {team_id: [(date iso, elo après le match), ...]}
      league   {team_id: dernier championnat joué}
      played   {team_id: nombre de matchs notés}
    """
    ratings, played, league, history, pre = {}, {}, {}, {}, {}
    cups = set(cups)
    for m in sorted(filter(_finished, matches), key=lambda m: m["utc_date"]):
        code = m.get("competition_code")
        hid, aid = m["home_team"]["id"], m["away_team"]["id"]
        for tid in (hid, aid):
            if tid not in ratings:
                pool = [ratings[t] for t, lg in league.items() if lg == code]
                ratings[tid] = (_quantile(pool, NEWCOMER_PCTL) if len(pool) >= MIN_TEAMS_FOR_PCTL
                                else BASE)
                played[tid] = 0
                history[tid] = []
            if code not in cups:
                league[tid] = code
        rh, ra = ratings[hid], ratings[aid]
        pre[m["match_id"]] = (rh, ra, min(played[hid], played[aid]))

        ft = m["score"]["fullTime"]
        gh, ga = ft["home"], ft["away"]
        result = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        delta = k * margin_multiplier(gh - ga) * (result - expected_home(rh, ra, home_adv))
        ratings[hid], ratings[aid] = rh + delta, ra - delta
        for tid in (hid, aid):
            played[tid] += 1
            history[tid].append((m["utc_date"], round(ratings[tid], 1)))
    return {"ratings": ratings, "pre": pre, "history": history, "league": league, "played": played}


# ---------------------------------------------------------------------------
# Modèle logistique ordonné : écart Elo -> probabilités 1N2
# ---------------------------------------------------------------------------
def _sig(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def outcome_probs(diff, coefs=None, home_adv=HOME_ADV):
    """Probabilités (domicile, nul, extérieur) pour un écart Elo dom - ext (hors
    avantage du terrain, ajouté ici)."""
    c = coefs or DEFAULT_LOGIT
    x = (diff + home_adv) / 100
    p_away = _sig(c["theta_away"] - c["beta"] * x)
    p_not_home = _sig(c["theta_draw"] - c["beta"] * x)
    return 1 - p_not_home, p_not_home - p_away, p_away


def _loglik(params, data):
    beta, t0, t1 = params
    if t1 <= t0:
        return -math.inf
    ll = 0.0
    for (x, y), w in data:
        s0, s1 = _sig(t0 - beta * x), _sig(t1 - beta * x)
        p = s0 if y == 0 else (s1 - s0 if y == 1 else 1 - s1)
        ll += w * math.log(max(p, 1e-12))
    return ll


def _grad(params, data):
    beta, t0, t1 = params
    gb = g0 = g1 = 0.0
    for (x, y), w in data:
        s0, s1 = _sig(t0 - beta * x), _sig(t1 - beta * x)
        d0, d1 = s0 * (1 - s0), s1 * (1 - s1)
        if y == 0:
            g0 += w * (1 - s0)
            gb -= w * x * (1 - s0)
        elif y == 2:
            g1 -= w * s1
            gb += w * x * s1
        else:
            den = max(s1 - s0, 1e-12)
            g0 -= w * d0 / den
            g1 += w * d1 / den
            gb -= w * x * (d1 - d0) / den
    return [gb, g0, g1]


def _solve3(a, b):
    """Résout le système linéaire 3×3 a·x = b (pivot de Gauss)."""
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            return None
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [vr - f * vi for vr, vi in zip(m[r], m[i])]
    return [m[i][3] / m[i][i] for i in range(3)]


def fit_ordered_logit(xs, ys, iters=30):
    """Maximum de vraisemblance (Newton, hessienne par différences finies).
    xs : écarts Elo /100 (avantage du terrain compris) ; ys : 0 ext, 1 nul, 2 dom.
    Les écarts sont regroupés au point Elo près (calcul rapide, même optimum)."""
    counts = {}
    for x, y in zip(xs, ys):
        key = (round(x, 2), y)
        counts[key] = counts.get(key, 0) + 1
    data = list(counts.items())
    params = [DEFAULT_LOGIT["beta"], DEFAULT_LOGIT["theta_away"], DEFAULT_LOGIT["theta_draw"]]
    ll = _loglik(params, data)
    for _ in range(iters):
        g = _grad(params, data)
        h, eps = [], 1e-4
        for j in range(3):
            up, dn = params[:], params[:]
            up[j] += eps
            dn[j] -= eps
            gu, gd = _grad(up, data), _grad(dn, data)
            h.append([(a - b) / (2 * eps) for a, b in zip(gu, gd)])
        step = _solve3([[h[r][c] for r in range(3)] for c in range(3)], [-v for v in g])
        if step is None:
            break
        t = 1.0
        while t > 1e-4:
            cand = [p + t * s for p, s in zip(params, step)]
            cll = _loglik(cand, data)
            if cll >= ll:
                break
            t /= 2
        else:
            break
        converged = abs(cll - ll) < 1e-7
        params, ll = cand, cll
        if converged:
            break
    return {"beta": params[0], "theta_away": params[1], "theta_draw": params[2]}


def training_set(matches, pre, home_adv=HOME_ADV, burn_in=BURN_IN):
    """(xs, ys) des matchs terminés où chaque équipe a déjà `burn_in` matchs notés."""
    xs, ys = [], []
    for m in matches:
        p = pre.get(m.get("match_id"))
        if not p or p[2] < burn_in or not _finished(m):
            continue
        ft = m["score"]["fullTime"]
        xs.append((p[0] - p[1] + home_adv) / 100)
        ys.append(2 if ft["home"] > ft["away"] else (1 if ft["home"] == ft["away"] else 0))
    return xs, ys


def fit_outcome_model(matches, pre, home_adv=HOME_ADV):
    """Coefficients 1N2 ajustés sur les matchs passés (valeurs par défaut si trop peu)."""
    xs, ys = training_set(matches, pre, home_adv)
    if len(xs) < MIN_FIT_MATCHES:
        return dict(DEFAULT_LOGIT, echantillon=len(xs), ajuste=False)
    return dict(fit_ordered_logit(xs, ys), echantillon=len(xs), ajuste=True)


# Backtest de référence (tools/backtest_historique.py) : 13 273 matchs de 8 championnats,
# saisons 2021-22 à 2026-27, coefficients ajustés sans regarder l'avenir.
BACKTEST = {
    "matchs": 13273,
    "periode": "2021-22 à 2026-27",
    "championnats": "Premier League, Championship, Liga, Serie A, Bundesliga, Ligue 1, Primeira Liga, Eredivisie",
    "log_loss": [
        {"modele": "Fréquences domicile / nul / extérieur", "valeur": 1.073, "reussite_pct": 43.7},
        {"modele": "Ancienne note /100 du site (tranches d'écart)", "valeur": 1.038, "reussite_pct": 47.8},
        {"modele": "Elo (site)", "valeur": 0.990, "reussite_pct": 51.8},
        {"modele": "Bet365 avant-match", "valeur": 0.971, "reussite_pct": 53.3},
        {"modele": "Pinnacle à la clôture", "valeur": 0.967, "reussite_pct": 53.5},
    ],
    "paris_roi_pct": [
        {"strategie": "Favori du modèle, cotes Bet365", "roi": -4.6},
        {"strategie": "« Value » (avantage ≥ 5 %), cotes Bet365", "roi": -10.0},
    ],
}


def elo_config():
    return {
        "principe": "Chaque équipe a une note Elo (1 500 au départ). Après chaque match, le vainqueur prend "
                    "des points au perdant, d'autant plus que le résultat était inattendu et l'écart de buts "
                    f"large (K = {K:g}). L'équipe à domicile reçoit un bonus de {HOME_ADV:g} points dans le "
                    "calcul. Les notes traversent les saisons (deux saisons précédentes chargées) et les coupes "
                    "d'Europe relient les championnats ; une équipe promue démarre au niveau des plus faibles "
                    "de son championnat.",
        "probabilites": "Les probabilités victoire / nul / défaite viennent d'un modèle logistique ordonné, "
                        "ajusté sur les matchs passés : pour un écart Elo donné, il reproduit la fréquence "
                        "observée de chaque issue. Les scores probables suivent une loi de Poisson dont la "
                        "répartition des buts est alignée sur ces probabilités.",
        "value": "Une « value » signale une issue dont la probabilité estimée dépasse d'au moins 5 % celle "
                 "qu'implique la cote du bookmaker. Sur l'historique, ces écarts n'ont pas été rentables : "
                 "les bookmakers restent plus précis que le modèle.",
        "backtest": BACKTEST,
    }
