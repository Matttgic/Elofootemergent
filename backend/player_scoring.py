"""Notation des joueurs (/100) — déterministe, fondée sur les données réelles
Understat de la saison en cours. Normalisation par 90 minutes.

Coefficients documentés (exposés via /api/scoring/config -> section joueurs).
Aucune donnée n'est inventée ; les valeurs absentes ne sont jamais fabriquées.
"""
from scoring import clamp

# Références "élite" (valeur ~100) pour la normalisation par 90 min
REF = {
    "buts_90": 1.0,        # 1 but/90 = niveau élite
    "xg_90": 1.0,
    "passes_90": 0.5,
    "occasions_90": 3.0,
    "xa_90": 0.5,
    "tirs_90": 4.0,
    "chain_90": 1.5,       # xGChain/90 (implication offensive)
}

PLAYER_WEIGHTS = {"buteur": 0.38, "creation": 0.30, "offensif": 0.22, "implication": 0.10}
RELIABILITY_MIN = 450.0     # minutes pour une fiabilité pleine (~5 matchs)
BASELINE = 40               # score de repli quand l'échantillon est faible

POSTES = {"F": "Attaquant", "M": "Milieu", "D": "Défenseur", "GK": "Gardien", "S": "Remplaçant"}


def _poste(position):
    if not position:
        return "N/D"
    tok = position.split()[0]
    if tok == "S" and len(position.split()) > 1:
        tok = position.split()[1]
    return POSTES.get(tok, "N/D")


def analyze_player(doc):
    minutes = doc.get("minutes") or 0
    per90 = 90.0 / minutes if minutes > 0 else 0.0
    g90 = doc["goals"] * per90
    a90 = doc["assists"] * per90
    sh90 = doc["shots"] * per90
    kp90 = doc["key_passes"] * per90
    xg90 = doc["xG"] * per90
    xa90 = doc["xA"] * per90
    chain90 = doc.get("xGChain", 0) * per90

    buteur = clamp((0.6 * g90 + 0.4 * xg90) / REF["buts_90"] * 100)
    creation = clamp((0.4 * (a90 / REF["passes_90"]) + 0.3 * (kp90 / REF["occasions_90"])
                      + 0.3 * (xa90 / REF["xa_90"])) * 100)
    offensif = clamp((0.5 * (xg90 + xa90) / 1.2 + 0.3 * (sh90 / REF["tirs_90"])
                      + 0.2 * (g90 + a90) / 1.2) * 100)
    implication = clamp(chain90 / REF["chain_90"] * 100)

    rel = clamp(minutes / RELIABILITY_MIN, 0, 1)
    c_but = PLAYER_WEIGHTS["buteur"] * buteur * rel
    c_cre = PLAYER_WEIGHTS["creation"] * creation * rel
    c_off = PLAYER_WEIGHTS["offensif"] * offensif * rel
    c_imp = PLAYER_WEIGHTS["implication"] * implication * rel
    c_base = BASELINE * (1 - rel)
    glob = round(c_but + c_cre + c_off + c_imp + c_base)

    def score(val, comps):
        return {"score": round(val), "composantes": comps}

    return {
        "player_id": doc["player_id"],
        "nom": doc["nom"],
        "poste": _poste(doc.get("position")),
        "team_id": doc.get("team_id"),
        "team_title": doc.get("team_title"),
        "competition_code": doc.get("competition_code"),
        "scores": {
            "global": {"score": glob, "composantes": [
                {"libelle": "Score buteur", "poids": "38%", "detail": f"{round(buteur)}/100", "contribution": round(c_but)},
                {"libelle": "Score création", "poids": "30%", "detail": f"{round(creation)}/100", "contribution": round(c_cre)},
                {"libelle": "Score offensif", "poids": "22%", "detail": f"{round(offensif)}/100", "contribution": round(c_off)},
                {"libelle": "Implication offensive", "poids": "10%", "detail": f"{round(implication)}/100", "contribution": round(c_imp)},
                {"libelle": "Ajustement temps de jeu", "poids": "—", "detail": f"{int(minutes)} min jouées (fiabilité {round(rel*100)}%)", "contribution": round(c_base)},
            ]},
            "buteur": score(buteur, [
                {"libelle": "Buts / 90 min", "poids": "60%", "detail": f"{g90:.2f}", "contribution": round(clamp(0.6 * g90 / REF['buts_90'] * 100))},
                {"libelle": "xG / 90 min", "poids": "40%", "detail": f"{xg90:.2f}", "contribution": round(clamp(0.4 * xg90 / REF['xg_90'] * 100))},
            ]),
            "creation": score(creation, [
                {"libelle": "Passes décisives / 90", "poids": "40%", "detail": f"{a90:.2f}", "contribution": round(0.4 * (a90 / REF['passes_90']) * 100)},
                {"libelle": "Occasions créées / 90", "poids": "30%", "detail": f"{kp90:.2f}", "contribution": round(0.3 * (kp90 / REF['occasions_90']) * 100)},
                {"libelle": "xA / 90", "poids": "30%", "detail": f"{xa90:.2f}", "contribution": round(0.3 * (xa90 / REF['xa_90']) * 100)},
            ]),
            "offensif": score(offensif, [
                {"libelle": "xG + xA / 90", "poids": "50%", "detail": f"{(xg90+xa90):.2f}", "contribution": round(clamp(0.5 * (xg90 + xa90) / 1.2 * 100))},
                {"libelle": "Tirs / 90", "poids": "30%", "detail": f"{sh90:.2f}", "contribution": round(0.3 * (sh90 / REF['tirs_90']) * 100)},
                {"libelle": "Buts + passes / 90", "poids": "20%", "detail": f"{(g90+a90):.2f}", "contribution": round(clamp(0.2 * (g90 + a90) / 1.2 * 100))},
            ]),
            "forme": {"score": round(implication), "composantes": [
                {"libelle": "Implication offensive (xGChain / 90)", "poids": "100%",
                 "detail": f"{chain90:.2f} — sur la saison en cours ({doc.get('games', 0)} matchs)",
                 "contribution": round(implication)},
            ]},
        },
        "stats": {
            "matchs": doc.get("games"),
            "minutes": int(minutes),
            "buts": doc["goals"],
            "passes_decisives": doc["assists"],
            "tirs": doc["shots"],
            "occasions_creees": doc["key_passes"],
            "xG": round(doc["xG"], 2),
            "xA": round(doc["xA"], 2),
            "cartons_jaunes": doc.get("yellow", 0),
            "cartons_rouges": doc.get("red", 0),
            "buts_par_90": round(g90, 2),
            "passes_par_90": round(a90, 2),
        },
    }


def player_scoring_config():
    return {
        "source": "Understat (saison en cours) — statistiques individuelles réelles, xG/xA inclus.",
        "couverture": "Premier League, La Liga, Bundesliga, Serie A, Ligue 1. "
                      "Portugal (Primeira Liga) et Pays-Bas (Eredivisie) : données joueurs indisponibles.",
        "normalisation": "Toutes les métriques sont ramenées à 90 minutes, puis normalisées sur 100.",
        "ajustement_echantillon": f"Le score global est pondéré par le temps de jeu (fiabilité pleine à "
                                  f"{int(RELIABILITY_MIN)} min) pour éviter qu'un joueur soit surnoté sur très peu de minutes.",
        "score_joueur": PLAYER_WEIGHTS,
        "references_par_90": REF,
    }
