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


def _avg(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _confiance(margin, faible, eleve):
    if margin >= eleve:
        return "Élevée"
    if margin >= faible:
        return "Modérée"
    return "Faible"


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

    h_scored = _avg([r["gf"] for r in (home_at_home or home_all)])
    h_conceded = _avg([r["gc"] for r in (home_at_home or home_all)])
    a_scored = _avg([r["gf"] for r in (away_at_away or away_all)])
    a_conceded = _avg([r["gc"] for r in (away_at_away or away_all)])

    exp_home = min(3.5, max(0.15, h_scored * a_conceded / lg_home_avg))
    exp_away = min(3.5, max(0.15, a_scored * h_conceded / lg_away_avg))
    exp_total = exp_home + exp_away

    signals = []

    # Over 2.5
    signals.append({
        "marche": "Plus de 2.5 buts",
        "statut": "Favorable" if exp_total >= 2.7 else ("Neutre" if exp_total >= 2.3 else "Défavorable"),
        "confiance": _confiance(abs(exp_total - 2.5), 0.35, 0.8),
        "valeur": round(exp_total, 2),
        "explication": f"Total de buts estimé à {exp_total:.2f} ({home_name} ≈ {exp_home:.2f}, "
                       f"{away_name} ≈ {exp_away:.2f}) d'après les buts marqués/encaissés récents.",
    })

    # Over 1.5
    signals.append({
        "marche": "Plus de 1.5 but",
        "statut": "Favorable" if exp_total >= 2.1 else ("Neutre" if exp_total >= 1.7 else "Défavorable"),
        "confiance": _confiance(abs(exp_total - 1.5), 0.4, 0.9),
        "valeur": round(exp_total, 2),
        "explication": f"Total de buts estimé à {exp_total:.2f}, à comparer au seuil de 1.5.",
    })

    # Under 2.5
    signals.append({
        "marche": "Moins de 2.5 buts",
        "statut": "Favorable" if exp_total <= 2.3 else ("Neutre" if exp_total <= 2.7 else "Défavorable"),
        "confiance": _confiance(abs(2.5 - exp_total), 0.35, 0.8),
        "valeur": round(exp_total, 2),
        "explication": f"Total de buts estimé à {exp_total:.2f} : profil de match {'fermé' if exp_total <= 2.3 else 'ouvert'}.",
    })

    # BTTS — les deux équipes marquent
    h_btts, h_hits, h_n = _rate(home_all, lambda r: r["gf"] >= 1 and r["gc"] >= 1)
    a_btts, a_hits, a_n = _rate(away_all, lambda r: r["gf"] >= 1 and r["gc"] >= 1)
    btts = (h_btts + a_btts) / 2
    signals.append({
        "marche": "Les deux équipes marquent (BTTS)",
        "statut": "Favorable" if btts >= 0.6 else ("Neutre" if btts >= 0.45 else "Défavorable"),
        "confiance": _confiance(abs(btts - 0.5) * 2, 0.3, 0.7),
        "valeur": f"{round(btts * 100)}%",
        "explication": f"Les deux équipes ont marqué lors de {h_hits}/{h_n} des matchs de {home_name} "
                       f"et {a_hits}/{a_n} de ceux de {away_name}.",
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
        "avertissement": "Signaux statistiques indicatifs — en aucun cas des prédictions certaines.",
        "signaux": signals,
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
