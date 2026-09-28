"""Signaux de marché statistiques (jamais présentés comme des prédictions).

Chaque signal expose : marché, statut, confiance et une explication chiffrée
fondée sur les données réelles récentes des deux équipes.
"""
from scoring import extract_records, _norm_weights, _wavg


def _rate(recs, pred):
    if not recs:
        return 0.0, 0, 0
    hits = sum(1 for r in recs if pred(r))
    return hits / len(recs), hits, len(recs)


PRIOR_MATCHES = 4   # poids, en matchs, de la moyenne du championnat dans les moyennes d'équipe


def _shrunk(vals, prior):
    """Moyenne d'équipe ramenée vers la moyenne du championnat : avec 2 matchs,
    la ligue pèse 2/3 ; avec 10 matchs, moins de 30 %. Évite les espérances de
    buts extrêmes en début de saison."""
    return (sum(vals) + PRIOR_MATCHES * prior) / (len(vals) + PRIOR_MATCHES)


def _confiance(margin, faible, eleve):
    if margin >= eleve:
        return "Élevée"
    if margin >= faible:
        return "Modérée"
    return "Faible"


import math


def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _poisson_probs(mh, ma, maxg=8):
    ph = [_pois(i, mh) for i in range(maxg + 1)]
    pa = [_pois(j, ma) for j in range(maxg + 1)]
    p_home = p_draw = p_away = over25 = over15 = btts = 0.0
    grid = []
    for i in range(maxg + 1):
        for j in range(maxg + 1):
            p = ph[i] * pa[j]
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i + j >= 3:
                over25 += p
            if i + j >= 2:
                over15 += p
            if i >= 1 and j >= 1:
                btts += p
            grid.append((i, j, p))
    grid.sort(key=lambda x: x[2], reverse=True)
    scores = [{"score": f"{i}-{j}", "pct": round(p * 100, 1)} for i, j, p in grid[:3]]
    return {"domicile": p_home, "nul": p_draw, "exterieur": p_away,
            "over25": over25, "over15": over15, "under25": 1 - over25, "btts": btts,
            "scores": scores}


def _statut_prob(p, fav=0.55, neutre=0.45):
    return "Favorable" if p >= fav else ("Neutre" if p >= neutre else "Défavorable")


def build_signals(matches, home_id, away_id, home_name, away_name,
                  lg_home_avg=1.45, lg_away_avg=1.15):
    home_all = extract_records(matches, home_id)
    away_all = extract_records(matches, away_id)
    home_at_home = extract_records(matches, home_id, "HOME")
    away_at_away = extract_records(matches, away_id, "AWAY")

    if not home_all or not away_all:
        return {"disponible": False, "message": "Historique insuffisant pour générer des signaux."}

    # Modèle de force calibré sur la moyenne réelle du championnat (évite la
    # surestimation systématique des buts). Chaque espérance est ramenée à la
    # base de la ligue : un match "moyen" ≈ moyenne du championnat, seuls les
    # duels attaque forte / défense faible dépassent ce niveau.
    lg_home_avg = lg_home_avg if lg_home_avg and lg_home_avg > 0.2 else 1.45
    lg_away_avg = lg_away_avg if lg_away_avg and lg_away_avg > 0.2 else 1.15

    h_recs = home_at_home or home_all
    a_recs = away_at_away or away_all
    h_scored = _shrunk([r["gf"] for r in h_recs], lg_home_avg)
    h_conceded = _shrunk([r["gc"] for r in h_recs], lg_away_avg)
    a_scored = _shrunk([r["gf"] for r in a_recs], lg_away_avg)
    a_conceded = _shrunk([r["gc"] for r in a_recs], lg_home_avg)

    exp_home = min(3.5, max(0.15, h_scored * a_conceded / lg_home_avg))
    exp_away = min(3.5, max(0.15, a_scored * h_conceded / lg_away_avg))
    exp_total = exp_home + exp_away
    P = _poisson_probs(exp_home, exp_away)

    signals = []

    # Over 2.5 (probabilité Poisson)
    signals.append({
        "marche": "Plus de 2.5 buts",
        "statut": _statut_prob(P["over25"]),
        "confiance": _confiance(abs(P["over25"] - 0.5) * 2, 0.2, 0.5),
        "valeur": f"{round(P['over25'] * 100)}%",
        "explication": f"Probabilité estimée à {round(P['over25'] * 100)}% (total de buts attendu ≈ {exp_total:.2f} : "
                       f"{home_name} {exp_home:.2f}, {away_name} {exp_away:.2f}).",
    })

    # Over 1.5
    signals.append({
        "marche": "Plus de 1.5 but",
        "statut": _statut_prob(P["over15"], 0.65, 0.5),
        "confiance": _confiance(abs(P["over15"] - 0.5) * 2, 0.3, 0.6),
        "valeur": f"{round(P['over15'] * 100)}%",
        "explication": f"Probabilité estimée à {round(P['over15'] * 100)}% qu'il y ait au moins 2 buts.",
    })

    # Under 2.5
    signals.append({
        "marche": "Moins de 2.5 buts",
        "statut": _statut_prob(P["under25"]),
        "confiance": _confiance(abs(P["under25"] - 0.5) * 2, 0.2, 0.5),
        "valeur": f"{round(P['under25'] * 100)}%",
        "explication": f"Probabilité estimée à {round(P['under25'] * 100)}% : profil "
                       f"{'fermé' if P['under25'] >= 0.5 else 'ouvert'}.",
    })

    # BTTS — les deux équipes marquent (Poisson + fréquence récente)
    h_btts, h_hits, h_n = _rate(home_all, lambda r: r["gf"] >= 1 and r["gc"] >= 1)
    a_btts, a_hits, a_n = _rate(away_all, lambda r: r["gf"] >= 1 and r["gc"] >= 1)
    signals.append({
        "marche": "Les deux équipes marquent (BTTS)",
        "statut": _statut_prob(P["btts"]),
        "confiance": _confiance(abs(P["btts"] - 0.5) * 2, 0.2, 0.5),
        "valeur": f"{round(P['btts'] * 100)}%",
        "explication": f"Probabilité estimée à {round(P['btts'] * 100)}%. Historique : les deux équipes ont marqué "
                       f"dans {h_hits}/{h_n} des matchs de {home_name} et {a_hits}/{a_n} de {away_name}.",
    })

    # Avantage domicile
    h_home_rate, hh_hits, hh_n = _rate(home_at_home or home_all, lambda r: r["result"] == "W")
    a_away_rate, aa_hits, aa_n = _rate(away_at_away or away_all, lambda r: r["result"] == "W")
    edge = h_home_rate - a_away_rate
    signals.append({
        "marche": "Avantage domicile",
        "statut": "Favorable" if edge >= 0.25 else ("Neutre" if edge >= 0 else "Défavorable"),
        "confiance": _confiance(abs(edge), 0.2, 0.5),
        "valeur": f"{round(h_home_rate * 100)}% vs {round(a_away_rate * 100)}%",
        "explication": f"{home_name} gagne {hh_hits}/{hh_n} à domicile ; "
                       f"{away_name} gagne {aa_hits}/{aa_n} à l'extérieur.",
    })

    # Clean sheet domicile
    h_cs, hcs_hits, hcs_n = _rate(home_at_home or home_all, lambda r: r["gc"] == 0)
    a_scoring, asc_hits, asc_n = _rate(away_at_away or away_all, lambda r: r["gf"] >= 1)
    cs_favorable = h_cs >= 0.4 and a_scoring <= 0.6
    signals.append({
        "marche": f"Cage inviolée — {home_name}",
        "statut": "Favorable" if cs_favorable else ("Neutre" if h_cs >= 0.3 else "Défavorable"),
        "confiance": _confiance(h_cs, 0.3, 0.5),
        "valeur": f"{round(h_cs * 100)}%",
        "explication": f"{home_name} garde sa cage inviolée {hcs_hits}/{hcs_n} à domicile ; "
                       f"{away_name} marque dans {asc_hits}/{asc_n} de ses matchs à l'extérieur.",
    })

    return {
        "disponible": True,
        "buts_estimes": {"total": round(exp_total, 2), "domicile": round(exp_home, 2), "exterieur": round(exp_away, 2)},
        "probabilites": {
            "domicile_pct": round(P["domicile"] * 100),
            "nul_pct": round(P["nul"] * 100),
            "exterieur_pct": round(P["exterieur"] * 100),
            "scores_probables": P["scores"],
        },
        "avertissement": "Signaux statistiques indicatifs — en aucun cas des prédictions certaines.",
        "signaux": signals,
    }


def h2h_insight(confrontations):
    """Signal fondé sur les confrontations directes (retourne None si < 3 matchs)."""
    if not confrontations or len(confrontations) < 3:
        return None
    n = len(confrontations)
    over = btts = tot = 0
    for c in confrontations:
        try:
            gh, ga = [int(x) for x in c["score"].split(" - ")]
        except (ValueError, KeyError):
            continue
        tot += gh + ga
        if gh + ga >= 3:
            over += 1
        if gh >= 1 and ga >= 1:
            btts += 1
    moy = tot / n
    return {
        "marche": "Historique direct",
        "statut": "Favorable" if over / n >= 0.6 else ("Neutre" if over / n >= 0.4 else "Défavorable"),
        "confiance": "Modérée" if n >= 5 else "Faible",
        "valeur": f"{moy:.1f} buts/match",
        "explication": f"Sur {n} confrontations directes : {moy:.1f} buts en moyenne, "
                       f"plus de 2.5 buts dans {over}/{n} et BTTS dans {btts}/{n}.",
    }


def head_to_head(matches, home_id, away_id):
    out = []
    ids = {home_id, away_id}
    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        h = (m.get("home_team") or {}).get("id")
        a = (m.get("away_team") or {}).get("id")
        if {h, a} != ids:
            continue
        ft = (m.get("score") or {}).get("fullTime") or {}
        if ft.get("home") is None:
            continue
        out.append({
            "date": m.get("utc_date"),
            "domicile": (m.get("home_team") or {}).get("shortName") or (m.get("home_team") or {}).get("name"),
            "exterieur": (m.get("away_team") or {}).get("shortName") or (m.get("away_team") or {}).get("name"),
            "score": f"{ft.get('home')} - {ft.get('away')}",
        })
    out.sort(key=lambda r: r["date"] or "", reverse=True)
    return out[:8]
