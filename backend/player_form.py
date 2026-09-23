"""Forme récente d'un joueur, calculée sur ses vrais derniers matchs (Understat).

Pondération décroissante (matchs les plus récents = poids le plus fort),
cohérente avec la notation des équipes. Aucune donnée n'est inventée.
"""
from scoring import clamp, _norm_weights, _wavg
from player_ingest import _norm, _i, _f

RECENT_N = 6  # nombre de derniers matchs pris en compte


def _same(a, b):
    na, nb = _norm(a), _norm(b)
    return bool(na) and (na == nb or na in nb or nb in na)


def _res(pour, contre):
    if pour > contre:
        return "W"
    if pour == contre:
        return "D"
    return "L"


def compute_recent_form(matches, team_title, n=RECENT_N):
    played = [m for m in matches if _i(m.get("time")) > 0]
    played.sort(key=lambda m: m.get("date") or "", reverse=True)
    recent = played[:n]
    if not recent:
        return None

    w = _norm_weights(len(recent))
    ga_vals, xgxa_vals, detail = [], [], []
    tot_g = tot_a = tot_min = 0
    for m in recent:
        g, a, tm = _i(m["goals"]), _i(m["assists"]), _i(m["time"])
        xg, xa = _f(m["xG"]), _f(m["xA"])
        ga_vals.append(g + a)
        xgxa_vals.append(xg + xa)
        tot_g += g
        tot_a += a
        tot_min += tm
        ht, at = m.get("h_team"), m.get("a_team")
        hg, ag = _i(m.get("h_goals")), _i(m.get("a_goals"))
        if _same(ht, team_title):
            lieu, opp, res = "Domicile", at, _res(hg, ag)
        elif _same(at, team_title):
            lieu, opp, res = "Extérieur", ht, _res(ag, hg)
        else:
            lieu, opp, res = "?", (at or ht), None
        detail.append({"date": m.get("date"), "adversaire": opp, "lieu": lieu,
                       "buts": g, "passes": a, "minutes": tm, "resultat": res})

    wg_ga = _wavg(ga_vals, w)      # buts+passes pondérés récence
    wg_xg = _wavg(xgxa_vals, w)    # xG+xA pondérés récence
    c_ga = clamp(0.5 * wg_ga * 100)
    c_xg = clamp(0.5 * wg_xg * 100)
    raw = c_ga + c_xg
    if raw > 100:                  # normalise pour que les contributions somment au score affiché
        c_ga, c_xg = c_ga * 100 / raw, c_xg * 100 / raw
    score = round(clamp(raw))

    return {
        "form_score": {"score": score, "composantes": [
            {"libelle": f"Buts + passes (pondérés, {len(recent)} derniers matchs)", "poids": "50%",
             "detail": f"{tot_g} buts, {tot_a} passes", "contribution": round(c_ga)},
            {"libelle": "xG + xA récents (pondérés)", "poids": "50%",
             "detail": f"{wg_xg:.2f} par match", "contribution": round(c_xg)},
        ]},
        "resume": {"matchs": len(recent), "buts": tot_g, "passes": tot_a, "minutes": tot_min},
        "matchs": detail,
    }


def compute_fotmob_form(recent_matches, n=RECENT_N):
    """Forme récente d'un joueur FotMob (Portugal/Pays-Bas) à partir de ses vrais
    derniers matchs. FotMob ne fournit pas le xG/xA par match : on combine la
    production offensive (buts+passes) et la note de match FotMob, pondérées par
    la récence. Aucune donnée n'est inventée."""
    played = [m for m in recent_matches
              if m.get("playedInMatch") and _i(m.get("minutesPlayed")) > 0]
    played.sort(key=lambda m: (m.get("matchDate") or {}).get("utcTime") or "", reverse=True)
    recent = played[:n]
    if not recent:
        return None

    w = _norm_weights(len(recent))
    ga_vals, rating_vals, detail = [], [], []
    tot_g = tot_a = tot_min = 0
    for m in recent:
        g, a, tm = _i(m.get("goals")), _i(m.get("assists")), _i(m.get("minutesPlayed"))
        rating = _f((m.get("ratingProps") or {}).get("rating"))
        ga_vals.append(g + a)
        rating_vals.append(clamp((rating - 6.0) / 3.0 * 100) if rating else 0)
        tot_g += g
        tot_a += a
        tot_min += tm
        home = bool(m.get("isHomeTeam"))
        hg, ag = _i(m.get("homeScore")), _i(m.get("awayScore"))
        pour, contre = (hg, ag) if home else (ag, hg)
        detail.append({
            "date": (m.get("matchDate") or {}).get("utcTime"),
            "adversaire": m.get("opponentTeamName"),
            "lieu": "Domicile" if home else "Extérieur",
            "buts": g, "passes": a, "minutes": tm, "resultat": _res(pour, contre),
        })

    wg_ga = _wavg(ga_vals, w)
    wg_rating = _wavg(rating_vals, w)
    c_ga = clamp(0.55 * clamp(wg_ga * 100))
    c_rating = clamp(0.45 * wg_rating)
    score = round(clamp(c_ga + c_rating))

    return {
        "form_score": {"score": score, "composantes": [
            {"libelle": f"Buts + passes (pondérés, {len(recent)} derniers matchs)", "poids": "55%",
             "detail": f"{tot_g} buts, {tot_a} passes", "contribution": round(c_ga)},
            {"libelle": "Note de match FotMob (pondérée)", "poids": "45%",
             "detail": f"{(wg_rating/100*3+6):.2f}/10 en moyenne", "contribution": round(c_rating)},
        ]},
        "resume": {"matchs": len(recent), "buts": tot_g, "passes": tot_a, "minutes": tot_min},
        "matchs": detail,
    }
