"""Notation des joueurs (/100) — déterministe, fondée sur les données réelles
de la saison en cours (Understat pour les 5 grands championnats ; FotMob pour
le Portugal et les Pays-Bas). Normalisation par 90 minutes.

Échelle recalibrée (exigeante) : seuls les profils réellement élites approchent
90-100, un bon joueur se situe ~65-75, un joueur moyen ~45-55. La logique reste
déterministe et ne fabrique aucune donnée : les valeurs absentes sont ignorées.
"""
from scoring import clamp

# Références "élite" (par 90 min) : niveau atteint par le meilleur profil d'un
# grand championnat. Plus la référence est haute, plus l'échelle est exigeante.
REF = {
    "buts_90": 0.95,
    "xg_90": 0.80,
    "passes_90": 0.45,
    "occasions_90": 2.60,
    "xa_90": 0.45,
    "xga_90": 1.15,        # (xG + xA) / 90
    "ga_90": 1.15,         # (buts + passes) / 90
    "tirs_90": 3.80,
    "chain_90": 1.40,      # xGChain/90 (implication offensive)
}

# Courbe de calibration : score = 100 * r^EXP (r = production / référence élite).
# EXP < 1 étale le haut de l'échelle ; r est plafonné pour éviter tout dépassement.
CURVE_EXP = 0.72

PLAYER_WEIGHTS = {"buteur": 0.38, "creation": 0.30, "offensif": 0.22, "implication": 0.10}
RELIABILITY_MIN = 900.0     # minutes pour une fiabilité pleine (~10 matchs)
BASELINE = 38               # score de repli quand l'échantillon est faible

POSTES = {"F": "Attaquant", "M": "Milieu", "D": "Défenseur", "GK": "Gardien", "S": "Remplaçant"}


def _curve(r):
    """Applique la courbe de calibration à un ratio production/référence."""
    r = clamp(r, 0.0, 1.05)
    return clamp((r ** CURVE_EXP) * 100)


def _split(score, parts):
    """Répartit `score` proportionnellement aux ratios `parts` (somme = score)."""
    tot = sum(parts)
    if tot <= 0:
        return [0 for _ in parts]
    return [round(score * p / tot) for p in parts]


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

    # --- Buteur ---
    b1 = 0.60 * (g90 / REF["buts_90"])
    b2 = 0.40 * (xg90 / REF["xg_90"])
    buteur_raw = _curve(b1 + b2)

    # --- Création ---
    c1 = 0.45 * (a90 / REF["passes_90"])
    c2 = 0.30 * (kp90 / REF["occasions_90"])
    c3 = 0.25 * (xa90 / REF["xa_90"])
    creation_raw = _curve(c1 + c2 + c3)

    # --- Offensif ---
    o1 = 0.50 * ((xg90 + xa90) / REF["xga_90"])
    o2 = 0.30 * (sh90 / REF["tirs_90"])
    o3 = 0.20 * ((g90 + a90) / REF["ga_90"])
    offensif_raw = _curve(o1 + o2 + o3)

    # --- Implication offensive ---
    implication_raw = _curve(chain90 / REF["chain_90"])

    # Ajustement fiabilité : sur un petit échantillon (début de saison, peu de
    # minutes), les cadences par 90 sont volatiles. On ramène chaque sous-score
    # vers un repli neutre proportionnellement au temps de jeu — cela évite
    # qu'un joueur soit surnoté (buteur à 100 sur 3 matchs, par ex.).
    rel = clamp(minutes / RELIABILITY_MIN, 0, 1)

    def _adj(raw):
        return raw * rel + BASELINE * (1 - rel)

    buteur = _adj(buteur_raw)
    creation = _adj(creation_raw)
    offensif = _adj(offensif_raw)
    implication = _adj(implication_raw)

    def _components(raw, adj, ratios, rows):
        """Contributions basées sur le sous-score brut + une ligne d'ajustement
        fiabilité, de sorte que la somme des lignes = score affiché."""
        parts = _split(raw, ratios)
        comps = [{"libelle": l, "poids": p, "detail": d, "contribution": parts[i]}
                 for i, (l, p, d) in enumerate(rows)]
        fiab = round(adj) - sum(parts)
        if fiab != 0:
            comps.append({"libelle": "Ajustement fiabilité", "poids": "—",
                          "detail": f"fiabilité {round(rel*100)}% ({int(minutes)} min)",
                          "contribution": fiab})
        return comps

    c_but = PLAYER_WEIGHTS["buteur"] * buteur
    c_cre = PLAYER_WEIGHTS["creation"] * creation
    c_off = PLAYER_WEIGHTS["offensif"] * offensif
    c_imp = PLAYER_WEIGHTS["implication"] * implication
    glob = round(c_but + c_cre + c_off + c_imp)

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
                {"libelle": "Fiabilité (temps de jeu)", "poids": "—", "detail": f"{int(minutes)} min jouées — fiabilité {round(rel*100)}%", "contribution": 0},
            ]},
            "buteur": score(buteur, _components(buteur_raw, buteur, [b1, b2], [
                ("Buts / 90 min", "60%", f"{g90:.2f}"),
                ("xG / 90 min", "40%", f"{xg90:.2f}"),
            ])),
            "creation": score(creation, _components(creation_raw, creation, [c1, c2, c3], [
                ("Passes décisives / 90", "45%", f"{a90:.2f}"),
                ("Occasions créées / 90", "30%", f"{kp90:.2f}"),
                ("xA / 90", "25%", f"{xa90:.2f}"),
            ])),
            "offensif": score(offensif, _components(offensif_raw, offensif, [o1, o2, o3], [
                ("xG + xA / 90", "50%", f"{(xg90+xa90):.2f}"),
                ("Tirs / 90", "30%", f"{sh90:.2f}"),
                ("Buts + passes / 90", "20%", f"{(g90+a90):.2f}"),
            ])),
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
        "source": "Understat (5 grands championnats) et FotMob (Portugal, Pays-Bas) — "
                  "statistiques individuelles réelles de la saison en cours, xG/xA inclus.",
        "couverture": "Premier League, La Liga, Bundesliga, Serie A, Ligue 1 (Understat) ; "
                      "Primeira Liga et Eredivisie (FotMob).",
        "normalisation": "Toutes les métriques sont ramenées à 90 minutes.",
        "calibration": f"Échelle exigeante : score = 100 × (production / référence élite)^{CURVE_EXP}. "
                       "Un profil réellement élite approche 90-100, un bon joueur ~65-75, un joueur moyen ~45-55.",
        "ajustement_echantillon": f"Le score global est pondéré par le temps de jeu (fiabilité pleine à "
                                  f"{int(RELIABILITY_MIN)} min) pour éviter qu'un joueur soit surnoté sur très peu de minutes.",
        "score_joueur": PLAYER_WEIGHTS,
        "references_par_90": REF,
        "note_source": "FotMob ne fournit pas le xGChain : l'implication offensive y est approximée par xG + xA.",
    }
