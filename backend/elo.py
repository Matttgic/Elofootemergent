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


def outcome_probs(diff, coefs=None, home_adv=HOME_ADV, xg_diff=None):
    """Probabilités (domicile, nul, extérieur) pour un écart Elo dom - ext (hors
    avantage du terrain, ajouté ici) et, si le modèle en tient compte, l'écart de
    forme xG entre les deux équipes."""
    c = coefs or DEFAULT_LOGIT
    x = (diff + home_adv) / 100
    eta = c["beta"] * x
    if xg_diff is not None and "beta_xg" in c:
        eta += c["beta_xg"] * xg_diff
    return ordered_probs(eta, c)


def ordered_probs(eta, coefs):
    """(domicile, nul, extérieur) pour l'indice eta (somme coefficient × variable) du
    modèle logistique ordonné."""
    p_away = _sig(coefs["theta_away"] - eta)
    p_not_home = _sig(coefs["theta_draw"] - eta)
    return 1 - p_not_home, p_not_home - p_away, p_away


def _unpack(params, k):
    return params[:k], params[k], params[k + 1]


def _loglik(params, data, k):
    beta, t0, t1 = _unpack(params, k)
    if t1 <= t0:
        return -math.inf
    ll = 0.0
    for (x, y), w in data:
        eta = sum(b * v for b, v in zip(beta, x))
        s0, s1 = _sig(t0 - eta), _sig(t1 - eta)
        p = s0 if y == 0 else (s1 - s0 if y == 1 else 1 - s1)
        ll += w * math.log(max(p, 1e-12))
    return ll


def _grad(params, data, k):
    beta, t0, t1 = _unpack(params, k)
    gb, g0, g1 = [0.0] * k, 0.0, 0.0
    for (x, y), w in data:
        eta = sum(b * v for b, v in zip(beta, x))
        s0, s1 = _sig(t0 - eta), _sig(t1 - eta)
        d0, d1 = s0 * (1 - s0), s1 * (1 - s1)
        if y == 0:
            g0 += w * (1 - s0)
            coef = -(1 - s0)
        elif y == 2:
            g1 -= w * s1
            coef = s1
        else:
            den = max(s1 - s0, 1e-12)
            g0 -= w * d0 / den
            g1 += w * d1 / den
            coef = -(d1 - d0) / den
        for j in range(k):
            gb[j] += w * x[j] * coef
    return gb + [g0, g1]


def _solve(a, b):
    """Résout le système linéaire a·x = b (pivot de Gauss) ; None si singulier."""
    n = len(b)
    m = [row[:] + [v] for row, v in zip(a, b)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        m[i], m[p] = m[p], m[i]
        if abs(m[i][i]) < 1e-12:
            return None
        for r in range(n):
            if r != i:
                f = m[r][i] / m[i][i]
                m[r] = [vr - f * vi for vr, vi in zip(m[r], m[i])]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_ordered_logit(xs, ys, iters=30):
    """Maximum de vraisemblance (Newton, hessienne par différences finies).
    xs : écarts Elo /100 (avantage du terrain compris), ou tuples (écart Elo /100,
    écart de forme xG) ; ys : 0 ext, 1 nul, 2 dom. Les valeurs sont regroupées au
    centième près (calcul rapide, même optimum)."""
    rows = [x if isinstance(x, (tuple, list)) else (x,) for x in xs]
    k = len(rows[0]) if rows else 1
    counts = {}
    for x, y in zip(rows, ys):
        key = (tuple(round(v, 2) for v in x), y)
        counts[key] = counts.get(key, 0) + 1
    data = list(counts.items())
    params = [DEFAULT_LOGIT["beta"]] + [0.0] * (k - 1) + [DEFAULT_LOGIT["theta_away"], DEFAULT_LOGIT["theta_draw"]]
    n = k + 2
    ll = _loglik(params, data, k)
    for _ in range(iters):
        g = _grad(params, data, k)
        h, eps = [], 1e-4
        for j in range(n):
            up, dn = params[:], params[:]
            up[j] += eps
            dn[j] -= eps
            gu, gd = _grad(up, data, k), _grad(dn, data, k)
            h.append([(a - b) / (2 * eps) for a, b in zip(gu, gd)])
        step = _solve([[h[r][c] for r in range(n)] for c in range(n)], [-v for v in g])
        if step is None:
            break
        t = 1.0
        while t > 1e-4:
            cand = [p + t * s for p, s in zip(params, step)]
            cll = _loglik(cand, data, k)
            if cll >= ll:
                break
            t /= 2
        else:
            break
        converged = abs(cll - ll) < 1e-7
        params, ll = cand, cll
        if converged:
            break
    out = {"beta": params[0], "betas": params[:k], "theta_away": params[k], "theta_draw": params[k + 1]}
    if k == 2:
        out["beta_xg"] = params[1]
    return out


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


# ---------------------------------------------------------------------------
# Forme xG (Understat, 5 grands championnats) : 2e variable du modèle 1N2
# ---------------------------------------------------------------------------
XG_HALF_LIFE = 15        # demi-vie, en matchs, de la moyenne des écarts d'xG
XG_MIN_MATCHES = 3       # matchs avec xG requis pour chaque équipe
# Coefficients Elo + xG par défaut (ajustés sur 12 700 matchs des 5 grands championnats)
DEFAULT_LOGIT_XG = {"beta": 0.13, "beta_xg": 0.80, "theta_away": -0.83, "theta_draw": 0.40}


def _xg(m):
    xg = m.get("xg") or {}
    h, a = xg.get("home"), xg.get("away")
    return (h, a) if h is not None and a is not None else None


def xg_form(matches, half_life=XG_HALF_LIFE):
    """Écart d'xG récent de chaque équipe (xG pour − xG contre, moyenne à décroissance
    exponentielle : un match compte moitié moins `half_life` matchs plus tard), AVANT
    chaque match terminé, et sa valeur actuelle. Seuls les matchs avec xG comptent.
    Retourne {"pre": {match_id: (forme_dom, n_dom, forme_ext, n_ext)},
              "teams": {team_id: (forme, n)}} (n = nombre de matchs avec xG)."""
    decay = 0.5 ** (1 / half_life)
    state, pre = {}, {}

    def value(s):
        return s[0] / s[1] if s[1] else 0.0

    for m in sorted(filter(_finished, matches), key=lambda m: m["utc_date"]):
        hid, aid = m["home_team"]["id"], m["away_team"]["id"]
        sh = state.setdefault(hid, [0.0, 0.0, 0])
        sa = state.setdefault(aid, [0.0, 0.0, 0])
        pre[m["match_id"]] = (value(sh), sh[2], value(sa), sa[2])
        xg = _xg(m)
        if not xg:
            continue
        diff = xg[0] - xg[1]
        for s, sign in ((sh, 1), (sa, -1)):
            s[0] = decay * s[0] + sign * diff
            s[1] = decay * s[1] + 1
            s[2] += 1
    return {"pre": pre, "teams": {t: (value(s), s[2]) for t, s in state.items()}}


def xg_diff(form_dom, n_dom, form_ext, n_ext, min_matches=XG_MIN_MATCHES):
    """Écart de forme xG dom − ext, ou None si l'une des équipes a trop peu de matchs avec xG."""
    if n_dom < min_matches or n_ext < min_matches:
        return None
    return form_dom - form_ext


def fit_outcome_model_xg(matches, pre, xgf, home_adv=HOME_ADV, burn_in=BURN_IN):
    """Coefficients du modèle Elo + xG, ajustés sur les matchs où les deux équipes
    ont une forme xG (valeurs par défaut si l'échantillon est trop petit)."""
    xs, ys = [], []
    for m in matches:
        p, f = pre.get(m.get("match_id")), xgf["pre"].get(m.get("match_id"))
        if not p or not f or p[2] < burn_in or not _finished(m):
            continue
        d = xg_diff(*f)
        if d is None:
            continue
        ft = m["score"]["fullTime"]
        xs.append(((p[0] - p[1] + home_adv) / 100, d))
        ys.append(2 if ft["home"] > ft["away"] else (1 if ft["home"] == ft["away"] else 0))
    if len(xs) < MIN_FIT_MATCHES:
        return dict(DEFAULT_LOGIT_XG, echantillon=len(xs), ajuste=False)
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
        {"modele": "Elo", "valeur": 0.990, "reussite_pct": 51.8},
        {"modele": "Bet365 avant-match", "valeur": 0.971, "reussite_pct": 53.3},
        {"modele": "Pinnacle à la clôture", "valeur": 0.967, "reussite_pct": 53.5},
    ],
    "paris_roi_pct": [
        {"strategie": "Favori du modèle, cotes Bet365", "roi": -4.6},
        {"strategie": "« Value » (avantage ≥ 5 %), cotes Bet365", "roi": -10.0},
    ],
    # Apport des xG Understat, 5 grands championnats (7 800 matchs, mêmes saisons)
    "xg": {
        "matchs": 7800,
        "championnats": "Premier League, Liga, Serie A, Bundesliga, Ligue 1",
        "log_loss": [
            {"modele": "Elo seul", "valeur": 0.992, "brier": 0.592},
            {"modele": "Elo + tirs cadrés récents", "valeur": 0.987, "brier": 0.589},
            {"modele": "Elo + forme xG (site)", "valeur": 0.983, "brier": 0.586},
            {"modele": "Pinnacle à la clôture", "valeur": 0.968, "brier": 0.576},
        ],
    },
    # Note /100 comme modèle 1N2 (logit ordonné sur l'écart des notes avant le match), seule
    # ou combinée à l'Elo : 8 championnats, matchs où les deux notes existent (3 matchs joués)
    "notes": {
        "matchs": 11740,
        "log_loss": [
            {"modele": "Note /100 seule", "valeur": 1.0220, "brier": 0.6126, "reussite_pct": 49.1},
            {"modele": "Note /100 : global, attaque, défense, forme", "valeur": 1.0201, "brier": 0.6112,
             "reussite_pct": 49.3},
            {"modele": "Elo seul", "valeur": 0.9915, "brier": 0.5916, "reussite_pct": 51.7},
            {"modele": "Elo + note /100", "valeur": 0.9912, "brier": 0.5915, "reussite_pct": 51.8},
            {"modele": "Elo + les 4 notes", "valeur": 0.9909, "brier": 0.5912, "reussite_pct": 52.0},
            {"modele": "Mélange 90 % Elo / 10 % note", "valeur": 0.9910, "brier": 0.5912, "reussite_pct": 51.8},
            {"modele": "Pinnacle à la clôture", "valeur": 0.9697, "brier": 0.5770, "reussite_pct": 53.4},
        ],
        "conclusion": "Seule, la note /100 prévoit nettement moins bien que l'Elo (log-loss 1,022 contre "
                      "0,992, écart constaté chaque saison) : elle ne regarde que les 10 derniers matchs du "
                      "championnat en cours et ignore le terrain. Ajoutée à l'Elo, elle ne fait gagner que "
                      "0,0003 à 0,0006 : 15 à 30 fois moins que la forme xG (−0,009), du niveau de la marge "
                      "d'erreur, et la dernière saison est moins bonne ; avec la forme xG, elle dégrade même "
                      "légèrement le modèle (0,9824 → 0,9826). L'Elo contient déjà l'information de la note : "
                      "le modèle du site reste Elo (+ xG).",
    },
    # Classement unifié : toutes les méthodes sur les MÊMES matchs (5 grands championnats,
    # xG, notes et cotes disponibles). Indice de précision : 0 = simples fréquences
    # domicile / nul / extérieur, 100 = cotes Pinnacle à la clôture (calculé dans elo_config).
    "classement": {
        "matchs": 7144,
        "championnats": "Premier League, Liga, Serie A, Bundesliga, Ligue 1",
        "methodes": [
            {"id": "pinnacle", "modele": "Cotes Pinnacle à la clôture", "log_loss": 0.9673, "brier": 0.5750,
             "reussite_pct": 54.3, "marche": True},
            {"id": "bet365", "modele": "Cotes Bet365 avant-match", "log_loss": 0.9699, "brier": 0.5767,
             "reussite_pct": 53.9, "marche": True},
            {"id": "site", "modele": "Pronostic FootPulse (Elo + xG)", "log_loss": 0.9824, "brier": 0.5851,
             "reussite_pct": 52.9, "site": True},
            {"id": "elo", "modele": "Elo seul", "log_loss": 0.9915, "brier": 0.5914, "reussite_pct": 52.5},
            {"id": "note", "modele": "Note de forme /100", "log_loss": 1.0221, "brier": 0.6128, "reussite_pct": 49.8},
            {"id": "frequences", "modele": "Simples fréquences dom. / nul / ext.", "log_loss": 1.0739,
             "brier": 0.6499, "reussite_pct": 43.7},
        ],
    },
}


def ranking_with_index(block):
    """Ajoute à chaque méthode son indice de précision : part de l'écart de log-loss
    entre les simples fréquences (0) et les cotes Pinnacle (100) qu'elle comble."""
    ll = {m["id"]: m["log_loss"] for m in block["methodes"]}
    low, high = ll["frequences"], ll["pinnacle"]
    return {**block, "methodes": [{**m, "indice": round((low - m["log_loss"]) / (low - high) * 100)}
                                  for m in block["methodes"]]}


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
        "xg": "Dans les championnats suivis, le modèle ajoute la forme xG de chaque équipe : "
              "la différence entre les expected goals (xG, qualité des occasions) créés et concédés, "
              f"moyennée sur ses derniers matchs (demi-vie de {XG_HALF_LIFE} matchs). Sources : Understat "
              "pour les 5 grands championnats ; FotMob (données Opta) pour le Portugal, les Pays-Bas, le "
              "Championship et le Brésil. Les xG mesurent la domination mieux que le score, souvent décidé "
              f"par peu d'occasions. Il faut au moins {XG_MIN_MATCHES} matchs avec xG pour chaque équipe ; "
              "sinon (début de saison, promus, coupes), seul l'Elo est utilisé.",
        "value": "Une « value » signale une issue dont la probabilité estimée dépasse d'au moins 5 % celle "
                 "qu'implique la cote du bookmaker. Sur l'historique, ces écarts n'ont pas été rentables : "
                 "les bookmakers restent plus précis que le modèle.",
        "backtest": {**BACKTEST, "classement": ranking_with_index(BACKTEST["classement"])},
    }
