"""Moteur de notation déterministe et reproductible.

Aucune statistique n'est inventée. Tous les scores dérivent uniquement des
résultats réels des matchs récupérés (buts marqués/encaissés, résultats) et
du classement (force de l'adversaire). Les matchs récents sont davantage
pondérés via une décroissance géométrique.

Les tirs / occasions / xG ne sont PAS fournis par la source gratuite :
ils sont donc marqués "Donnée indisponible" et exclus des calculs, les
coefficients restant documentés ci-dessous.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Coefficients (documentés, exposés via /api/scoring/config)
# ---------------------------------------------------------------------------
DECAY = 0.85          # poids d'un match = DECAY^k (k=0 => match le plus récent)
MAX_MATCHES = 10      # fenêtre des matchs récents pris en compte
GOALS_SCALE = 3.0     # 3 buts/match => 100 pts (borne haute réaliste)

GLOBAL_WEIGHTS = {"forme": 0.40, "difference_buts": 0.25, "offensif": 0.175, "defensif": 0.175}
OFF_WEIGHTS = {"buts_par_match": 0.55, "regularite_offensive": 0.30, "forme_offensive_recente": 0.15}
DEF_WEIGHTS = {"buts_encaisses_par_match": 0.55, "clean_sheets": 0.30, "forme_defensive_recente": 0.15}

PARIS = ZoneInfo("Europe/Paris")


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _norm_weights(n):
    w = [DECAY ** k for k in range(n)]
    s = sum(w)
    return [x / s for x in w]


def _wavg(values, weights):
    return sum(v * w for v, w in zip(values, weights))


def paris_date(utc_iso: str) -> str:
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return dt.astimezone(PARIS).date().isoformat()


# ---------------------------------------------------------------------------
# Extraction des matchs d'une équipe
# ---------------------------------------------------------------------------
def extract_records(matches, team_id, venue=None):
    """Retourne les matchs TERMINÉS d'une équipe, du plus récent au plus ancien."""
    recs = []
    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        ft = (m.get("score") or {}).get("fullTime") or {}
        gh, ga = ft.get("home"), ft.get("away")
        if gh is None or ga is None:
            continue
        home, away = m.get("home_team") or {}, m.get("away_team") or {}
        if home.get("id") == team_id:
            v, gf, gc, opp = "HOME", gh, ga, away
        elif away.get("id") == team_id:
            v, gf, gc, opp = "AWAY", ga, gh, home
        else:
            continue
        if venue and v != venue:
            continue
        result = "W" if gf > gc else ("D" if gf == gc else "L")
        recs.append({
            "date": m.get("utc_date"),
            "matchday": m.get("matchday"),
            "venue": v,
            "opponent_id": opp.get("id"),
            "opponent_name": opp.get("shortName") or opp.get("name"),
            "gf": gf, "gc": gc, "result": result,
        })
    recs.sort(key=lambda r: r["date"] or "", reverse=True)
    return recs[:MAX_MATCHES]


def opp_strength(opponent_id, pos_map):
    """Force de l'adversaire dans [0,1] d'après le classement (1er = 1.0)."""
    info = pos_map.get(opponent_id)
    if not info:
        return 0.5
    pos, total = info
    if total <= 1:
        return 0.5
    return (total - pos) / (total - 1)


# ---------------------------------------------------------------------------
# Sous-scores
# ---------------------------------------------------------------------------
def _form_value(result, strength):
    """Valeur d'un résultat ajustée à la force de l'adversaire (dans [0,1])."""
    if result == "W":
        return 0.65 + 0.35 * strength   # battre un faible=0.65, un fort=1.0
    if result == "D":
        return 0.30 + 0.40 * strength   # nul contre faible=0.30, fort=0.70
    return 0.00 + 0.25 * strength        # perdre contre fort moins pénalisant


def compute_forme(recs, pos_map):
    if not recs:
        return None
    w = _norm_weights(len(recs))
    vals = [_form_value(r["result"], opp_strength(r["opponent_id"], pos_map)) for r in recs]
    score = clamp(_wavg(vals, w) * 100)
    return {
        "score": round(score),
        "composantes": [{
            "libelle": "Résultats pondérés (ajustés au niveau de l'adversaire)",
            "poids": "100%",
            "detail": "Victoire/Nul/Défaite pondérés par récence et force de l'adversaire",
            "contribution": round(score),
        }],
    }


def compute_offensif(recs, pos_map):
    if not recs:
        return None
    w = _norm_weights(len(recs))
    # buts ajustés au niveau de l'adversaire (limite les buts gonflés vs faibles)
    adj_gf = [r["gf"] * (0.75 + 0.25 * opp_strength(r["opponent_id"], pos_map)) for r in recs]
    gpm = _wavg(adj_gf, w)
    s_gpm = clamp(gpm / GOALS_SCALE * 100)
    reg = _wavg([1.0 if r["gf"] >= 1 else 0.0 for r in recs], w) * 100
    n3 = min(3, len(recs))
    w3 = _norm_weights(n3)
    s_recent = clamp(_wavg([recs[i]["gf"] for i in range(n3)], w3) / GOALS_SCALE * 100)
    c1 = OFF_WEIGHTS["buts_par_match"] * s_gpm
    c2 = OFF_WEIGHTS["regularite_offensive"] * reg
    c3 = OFF_WEIGHTS["forme_offensive_recente"] * s_recent
    return {
        "score": round(c1 + c2 + c3),
        "composantes": [
            {"libelle": "Buts/match (ajustés adversaire)", "poids": "55%", "detail": f"{gpm:.2f} buts/match", "contribution": round(c1)},
            {"libelle": "Régularité offensive", "poids": "30%", "detail": f"{reg:.0f}% de matchs avec ≥1 but", "contribution": round(c2)},
            {"libelle": "Forme offensive récente (3 derniers)", "poids": "15%", "detail": f"{_wavg([recs[i]['gf'] for i in range(n3)], w3):.2f} buts/match", "contribution": round(c3)},
            {"libelle": "Tirs cadrés / occasions / xG", "poids": "—", "detail": "Donnée indisponible (source gratuite)", "contribution": 0, "indisponible": True},
        ],
    }


def compute_defensif(recs, pos_map):
    if not recs:
        return None
    w = _norm_weights(len(recs))
    # buts encaissés ajustés au niveau de l'adversaire (symétrique de l'offensif) :
    # encaisser contre un fort pénalise moins que contre un faible
    adj_gc = [r["gc"] * (1.0 - 0.25 * opp_strength(r["opponent_id"], pos_map)) for r in recs]
    cpm = _wavg(adj_gc, w)
    s_conc = clamp((1 - cpm / GOALS_SCALE) * 100)
    cs = _wavg([1.0 if r["gc"] == 0 else 0.0 for r in recs], w) * 100
    n3 = min(3, len(recs))
    w3 = _norm_weights(n3)
    recent_gc = _wavg([recs[i]["gc"] for i in range(n3)], w3)
    s_recent = clamp((1 - recent_gc / GOALS_SCALE) * 100)
    c1 = DEF_WEIGHTS["buts_encaisses_par_match"] * s_conc
    c2 = DEF_WEIGHTS["clean_sheets"] * cs
    c3 = DEF_WEIGHTS["forme_defensive_recente"] * s_recent
    return {
        "score": round(c1 + c2 + c3),
        "composantes": [
            {"libelle": "Buts encaissés/match (ajustés adversaire)", "poids": "55%", "detail": f"{cpm:.2f} encaissés/match", "contribution": round(c1)},
            {"libelle": "Cages inviolées (clean sheets)", "poids": "30%", "detail": f"{cs:.0f}% de matchs sans encaisser", "contribution": round(c2)},
            {"libelle": "Forme défensive récente (3 derniers)", "poids": "15%", "detail": f"{recent_gc:.2f} encaissés/match", "contribution": round(c3)},
        ],
    }


def compute_global(recs, pos_map, offensif, defensif, forme):
    if not recs or not (offensif and defensif and forme):
        return None
    w = _norm_weights(len(recs))
    gd = _wavg([r["gf"] - r["gc"] for r in recs], w)
    s_gd = clamp(50 + gd * 15)
    c_forme = GLOBAL_WEIGHTS["forme"] * forme["score"]
    c_gd = GLOBAL_WEIGHTS["difference_buts"] * s_gd
    c_off = GLOBAL_WEIGHTS["offensif"] * offensif["score"]
    c_def = GLOBAL_WEIGHTS["defensif"] * defensif["score"]
    return {
        "score": round(c_forme + c_gd + c_off + c_def),
        "composantes": [
            {"libelle": "Forme (résultats récents)", "poids": "40%", "detail": f"Score de forme {forme['score']}/100", "contribution": round(c_forme)},
            {"libelle": "Différence de buts", "poids": "25%", "detail": f"{gd:+.2f} par match", "contribution": round(c_gd)},
            {"libelle": "Score offensif", "poids": "17.5%", "detail": f"{offensif['score']}/100", "contribution": round(c_off)},
            {"libelle": "Score défensif", "poids": "17.5%", "detail": f"{defensif['score']}/100", "contribution": round(c_def)},
        ],
    }


def rate_global(recs, pos_map):
    """Score global calculé à partir de matchs déjà extraits (None si aucun)."""
    if not recs:
        return None
    return compute_global(recs, pos_map, compute_offensif(recs, pos_map),
                          compute_defensif(recs, pos_map), compute_forme(recs, pos_map))


def _basic_stats(recs):
    if not recs:
        return None
    v = sum(1 for r in recs if r["result"] == "W")
    n = sum(1 for r in recs if r["result"] == "D")
    d = sum(1 for r in recs if r["result"] == "L")
    bm = sum(r["gf"] for r in recs)
    be = sum(r["gc"] for r in recs)
    cs = sum(1 for r in recs if r["gc"] == 0)
    played = len(recs)
    return {
        "matchs_analyses": played,
        "victoires": v, "nuls": n, "defaites": d,
        "buts_marques": bm, "buts_encaisses": be, "difference": bm - be,
        "buts_par_match": round(bm / played, 2), "encaisses_par_match": round(be / played, 2),
        "clean_sheets": cs,
        "forme_recente": [r["result"] for r in recs[:5]],
    }


def _match_perf(rec, strength):
    """Score de performance (0-100) d'un match unique pour le graphique."""
    result_c = _form_value(rec["result"], strength)
    margin_c = clamp(0.5 + (rec["gf"] - rec["gc"]) / 6.0, 0, 1)
    return round((0.7 * result_c + 0.3 * margin_c) * 100)


def _historique(recs, pos_map):
    out = []
    for r in recs:
        strength = opp_strength(r["opponent_id"], pos_map)
        out.append({
            "date": r["date"],
            "adversaire": r["opponent_name"],
            "lieu": "Domicile" if r["venue"] == "HOME" else "Extérieur",
            "resultat": r["result"],
            "buts_marques": r["gf"],
            "buts_encaisses": r["gc"],
            "score_obtenu": _match_perf(r, strength),
        })
    return out


def analyze_team(matches, pos_map, team_id, team_meta=None, standings_row=None):
    """Analyse complète d'une équipe. Retourne None si aucun match terminé."""
    recs = extract_records(matches, team_id)
    if not recs:
        return None
    off = compute_offensif(recs, pos_map)
    dfn = compute_defensif(recs, pos_map)
    frm = compute_forme(recs, pos_map)
    glb = compute_global(recs, pos_map, off, dfn, frm)

    home_recs = extract_records(matches, team_id, "HOME")
    away_recs = extract_records(matches, team_id, "AWAY")

    meta = team_meta or {}
    return {
        "team_id": team_id,
        "nom": meta.get("name"),
        "nom_court": meta.get("shortName") or meta.get("tla"),
        "logo": meta.get("crest"),
        "global": glb,
        "offensif": off,
        "defensif": dfn,
        "forme": frm,
        "domicile": rate_global(home_recs, pos_map),
        "exterieur": rate_global(away_recs, pos_map),
        "stats": _basic_stats(recs),
        "classement": standings_row,
        "historique": _historique(recs, pos_map),
    }


def scoring_config():
    return {
        "principe": "Notation déterministe et reproductible fondée uniquement sur des résultats réels. "
                    "Les matchs récents pèsent davantage (décroissance géométrique, coefficient "
                    f"DECAY={DECAY} par match en remontant, fenêtre de {MAX_MATCHES} matchs).",
        "anti_biais": "Les résultats, les buts marqués et les buts encaissés sont ajustés au niveau de "
                      "l'adversaire (via le classement) : marquer contre un faible compte moins, encaisser "
                      "contre un fort pénalise moins. Cela évite qu'une équipe soit surnotée en ne jouant "
                      "que des équipes faibles, ou sous-notée après un calendrier difficile.",
        "echelle": "Tous les scores sont normalisés sur 100.",
        "score_global": GLOBAL_WEIGHTS,
        "score_offensif": OFF_WEIGHTS,
        "score_defensif": DEF_WEIGHTS,
        "donnees_indisponibles": ["tirs", "tirs cadrés", "occasions", "possession", "xG", "xA",
                                  "statistiques individuelles des joueurs"],
        "note_donnees": "La source gratuite (football-data.org) ne fournit ni statistiques de tir/possession/xG "
                        "ni données individuelles des joueurs. Ces éléments sont marqués « Donnée indisponible » "
                        "et exclus des calculs.",
    }
