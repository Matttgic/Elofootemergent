"""Données et calculs partagés par les routes : chargement d'un championnat avec
ses analyses d'équipes, notes Elo et probabilités 1N2, statistiques, et leur cache.

Les analyses sont calculées une fois par championnat puis gardées en mémoire
(CACHE_TTL, et vidées après chaque ingestion via `invalidate_caches`) au lieu
d'être recalculées à chaque requête. Les calculs lourds tournent dans un thread
pour ne pas bloquer la boucle asynchrone ; un verrou par clé évite qu'une
expiration de cache déclenche le même calcul en parallèle.
"""
import asyncio
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from core import db
from elo import BURN_IN, HOME_ADV, fit_outcome_model, outcome_probs, run_elo
from ingest import COMPETITION_META, configured_codes, is_cup
from scoring import analyze_team

# Tranches d'écart Elo (avantage du terrain compris) pour les statistiques descriptives
ELO_BUCKETS = [(0, 25, "0–25"), (25, 50, "25–50"), (50, 75, "50–75"), (75, 100, "75–100"),
               (100, 150, "100–150"), (150, 200, "150–200"), (200, 10 ** 6, "200+")]
# Tranches de probabilité du favori (calibration du modèle, simulation de paris)
PROB_BUCKETS = [(0, 40, "< 40 %"), (40, 50, "40–50 %"), (50, 60, "50–60 %"),
                (60, 70, "60–70 %"), (70, 101, "≥ 70 %")]


def bucket_label(buckets, value):
    return next((label for lo, hi, label in buckets if lo <= value < hi), None)


CACHE_TTL = timedelta(minutes=10)
_comp_cache = {}                  # code -> (horodatage, CompData)
_elo_cache = {}                   # "ELO" -> (horodatage, EloData)
_stats_cache = {}                 # code | "ALL" -> (horodatage, dict)
_locks = defaultdict(asyncio.Lock)
_generation = 0                   # incrémenté à chaque invalidation


def invalidate_caches():
    """À appeler après une ingestion : les prochaines requêtes relisent la base."""
    global _generation
    _generation += 1
    _comp_cache.clear()
    _elo_cache.clear()
    _stats_cache.clear()


async def _cached(cache, key, loader):
    def fresh():
        hit = cache.get(key)
        return hit[1] if hit and datetime.now(timezone.utc) - hit[0] < CACHE_TTL else None

    value = fresh()
    if value is not None:
        return value
    async with _locks[(id(cache), key)]:
        value = fresh()
        if value is not None:
            return value
        gen = _generation
        value = await loader()
        if gen == _generation:   # pas d'ingestion terminée pendant le calcul
            cache[key] = (datetime.now(timezone.utc), value)
        return value


class CompData:
    """Un championnat : matchs, classement et analyse de chaque équipe.
    Partagé entre requêtes via le cache : ne pas modifier."""

    def __init__(self, matches, standings):
        self.matches = matches
        self.pos_map, self.rows = {}, {}
        table = (standings or {}).get("table") or []
        for entry in table:
            tid = (entry.get("team") or {}).get("id")
            if tid is None:
                continue
            self.pos_map[tid] = (entry.get("position"), len(table))
            self.rows[tid] = {
                "position": entry.get("position"),
                "points": entry.get("points"),
                "joues": entry.get("playedGames"),
                "victoires": entry.get("won"),
                "nuls": entry.get("draw"),
                "defaites": entry.get("lost"),
                "buts_pour": entry.get("goalsFor"),
                "buts_contre": entry.get("goalsAgainst"),
                "difference": entry.get("goalDifference"),
            }
        self.meta = {}
        for m in matches:
            for side in ("home_team", "away_team"):
                t = m.get(side) or {}
                if t.get("id") is not None:
                    self.meta[t["id"]] = t
        self.analyses = {tid: analyze_team(matches, self.pos_map, tid, t, self.rows.get(tid))
                         for tid, t in self.meta.items()}

    def team(self, team_id):
        """Analyse complète d'une équipe (None si aucun match terminé)."""
        return self.analyses.get(team_id)


async def comp_data(code):
    async def load():
        matches = await db.matches.find({"competition_code": code}, {"_id": 0}).to_list(2000)
        standings = await db.standings.find_one({"competition_code": code}, {"_id": 0})
        return await asyncio.to_thread(CompData, matches, standings)
    return await _cached(_comp_cache, code, load)


async def team_logos(codes):
    """{(code, team_id): url du logo} pour les championnats donnés (données en cache)."""
    logos = {}
    for c in set(codes):
        for tid, t in (await comp_data(c)).meta.items():
            if t.get("crest"):
                logos[(c, tid)] = t["crest"]
    return logos


def compact(analysis):
    if not analysis:
        return None

    def s(k):
        return analysis[k]["score"] if analysis.get(k) else None
    return {
        "team_id": analysis["team_id"],
        "nom": analysis["nom"],
        "nom_court": analysis["nom_court"],
        "logo": analysis["logo"],
        "global": s("global"),
        "offensif": s("offensif"),
        "defensif": s("defensif"),
        "forme": s("forme"),
        "forme_recente": (analysis.get("stats") or {}).get("forme_recente"),
        "classement": analysis.get("classement"),
    }


def match_summary(m):
    ft = (m.get("score") or {}).get("fullTime") or {}
    return {
        "match_id": m["match_id"],
        "competition_code": m["competition_code"],
        "utc_date": m.get("utc_date"),
        "match_date": m.get("match_date"),
        "status": m.get("status"),
        "matchday": m.get("matchday"),
        "score": {"home": ft.get("home"), "away": ft.get("away")},
    }


class EloData:
    """Elo de toutes les équipes (saisons précédentes + saison en cours, toutes
    compétitions) et modèle 1N2 ajusté. Partagé via le cache : ne pas modifier."""

    def __init__(self, matches, cups, current_ids):
        run = run_elo(matches, cups=cups)
        self.matches = matches
        self.current_ids = current_ids          # matchs de la saison en cours
        self.ratings, self.pre = run["ratings"], run["pre"]
        self.history, self.league, self.played = run["history"], run["league"], run["played"]
        self.coefs = fit_outcome_model(matches, self.pre)
        # Championnat de la saison en cours : une équipe sortie des championnats suivis
        # (reléguée plus bas, par exemple) n'est plus classée avec son ancien championnat.
        self.current_league = {}
        for m in sorted(matches, key=lambda m: m["utc_date"]):
            if m["match_id"] in current_ids and m.get("competition_code") not in cups:
                for side in ("home_team", "away_team"):
                    self.current_league[m[side]["id"]] = m["competition_code"]
        self.ranks = {}
        by_league = {}
        for tid, lg in self.current_league.items():
            by_league.setdefault(lg, []).append(tid)
        for tids in by_league.values():
            tids.sort(key=lambda t: -self.ratings[t])
            for i, tid in enumerate(tids, 1):
                self.ranks[tid] = (i, len(tids))

    def team(self, team_id):
        """Elo actuel d'une équipe et son rang dans son championnat (None si inconnue)."""
        if team_id not in self.ratings:
            return None
        rank = self.ranks.get(team_id)
        lg = self.current_league.get(team_id) or self.league.get(team_id)
        return {"elo": round(self.ratings[team_id]), "matchs": self.played.get(team_id, 0),
                "rang": rank[0] if rank else None, "sur": rank[1] if rank else None,
                "championnat": lg, "championnat_nom": COMPETITION_META.get(lg, {}).get("nom")}

    def match_ratings(self, m):
        """(elo_dom, elo_ext, matchs_min) avant le match : figés s'il est terminé,
        sinon notes actuelles. None si une équipe n'a encore aucun match noté."""
        if m.get("match_id") in self.pre:
            return self.pre[m["match_id"]]
        hid = (m.get("home_team") or {}).get("id")
        aid = (m.get("away_team") or {}).get("id")
        if hid not in self.ratings or aid not in self.ratings:
            return None
        return self.ratings[hid], self.ratings[aid], min(self.played[hid], self.played[aid])


async def elo_data():
    async def load():
        proj = {"_id": 0, "match_id": 1, "competition_code": 1, "utc_date": 1, "status": 1,
                "home_team.id": 1, "away_team.id": 1, "score.fullTime": 1}
        current = await db.matches.find({"status": "FINISHED"}, proj).to_list(50000)
        older = await db.matches_history.find({"status": "FINISHED"}, proj).to_list(50000)
        ids = {m["match_id"] for m in current}
        matches = current + [m for m in older if m["match_id"] not in ids]
        cups = [c for c in COMPETITION_META if is_cup(c)]
        return await asyncio.to_thread(EloData, matches, cups, ids)
    return await _cached(_elo_cache, "ELO", load)


def prediction(eld, m, home_name, away_name):
    """Probabilités 1N2 du modèle Elo pour un match (None si une équipe est inconnue)."""
    r = eld.match_ratings(m)
    if not r:
        return None
    rh, ra, n = r
    ph, pn, pa = outcome_probs(rh - ra, eld.coefs)
    fav_home = ph >= pa
    return {
        "elo_domicile": round(rh), "elo_exterieur": round(ra), "avantage_terrain": round(HOME_ADV),
        "ecart": round(abs(rh + HOME_ADV - ra)),
        "domicile_pct": round(ph * 100, 1), "nul_pct": round(pn * 100, 1), "exterieur_pct": round(pa * 100, 1),
        "favori": home_name if fav_home else away_name,
        "favori_cote": "domicile" if fav_home else "exterieur",
        "favori_pct": round(max(ph, pa) * 100, 1),
        "matchs_min": n,
        "fiable": n >= BURN_IN,
    }


def _outcome(m):
    ft = m["score"]["fullTime"]
    return 2 if ft["home"] > ft["away"] else (1 if ft["home"] == ft["away"] else 0)


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else None


async def stats_analytics(code=None):
    """Statistiques descriptives et qualité du modèle. Chaque match terminé est comparé
    aux notes Elo que les deux équipes avaient AVANT son coup d'envoi."""
    async def load():
        eld = await elo_data()
        leagues = {c for c in ([code] if code else configured_codes()) if not is_cup(c)}
        return await asyncio.to_thread(_compute_stats, eld, leagues)
    return await _cached(_stats_cache, code or "ALL", load)


def _compute_stats(eld, leagues):
    rated = [m for m in eld.matches if m.get("competition_code") in leagues
             and m["match_id"] in eld.pre and eld.pre[m["match_id"]][2] >= BURN_IN]
    fav = {0: 0, 1: 0, 2: 0}                  # 2 = le favori Elo gagne, 1 = nul, 0 = il perd
    home_out = {0: 0, 1: 0, 2: 0}
    buckets = {label: {0: 0, 1: 0, 2: 0} for _, _, label in ELO_BUCKETS}
    scores = {label: {} for _, _, label in ELO_BUCKETS}
    for m in rated:
        rh, ra, _ = eld.pre[m["match_id"]]
        diff = rh + HOME_ADV - ra
        y = _outcome(m)
        home_out[y] += 1
        fav_home = diff >= 0
        res = y if fav_home else 2 - y
        fav[res] += 1
        label = bucket_label(ELO_BUCKETS, abs(diff))
        buckets[label][res] += 1
        ft = m["score"]["fullTime"]
        sk = f"{ft['home']}-{ft['away']}" if fav_home else f"{ft['away']}-{ft['home']}"
        scores[label][sk] = scores[label].get(sk, 0) + 1

    par_ecart = []
    for _, _, label in ELO_BUCKETS:
        b, n = buckets[label], sum(buckets[label].values())
        tot = sum(scores[label].values())
        top = sorted(scores[label].items(), key=lambda x: (x[1], x[0]), reverse=True)[:4]
        par_ecart.append({"tranche": label, "matchs": n, "favori_gagne_pct": _pct(b[2], n),
                          "nul_pct": _pct(b[1], n), "outsider_gagne_pct": _pct(b[0], n),
                          "scores_frequents": [{"score": k, "pct": _pct(v, tot), "n": v} for k, v in top]})

    n_fav, n_home = sum(fav.values()), sum(home_out.values())
    return {
        "disponible": len(rated) > 0,
        "echantillon": len(rated),
        "echantillon_saison": sum(1 for m in rated if m["match_id"] in eld.current_ids),
        "favori_elo": {"victoires_pct": _pct(fav[2], n_fav), "nuls_pct": _pct(fav[1], n_fav),
                       "defaites_pct": _pct(fav[0], n_fav)},
        "avantage_domicile": {"domicile_pct": _pct(home_out[2], n_home), "nul_pct": _pct(home_out[1], n_home),
                              "exterieur_pct": _pct(home_out[0], n_home)},
        "par_ecart_elo": par_ecart,
        "modele": _model_quality(eld, rated),
        "note": "Statistiques descriptives : chaque match terminé est comparé aux notes Elo que les deux "
                "équipes avaient avant le coup d'envoi (avantage du terrain de "
                f"{int(HOME_ADV)} points compris), une fois au moins {BURN_IN} matchs joués par chacune. "
                "Championnats uniquement, saisons précédentes comprises quand elles sont disponibles.",
    }


def _model_quality(eld, rated):
    """Log-loss, score de Brier et taux de réussite des probabilités 1N2 sur les matchs
    de la saison en cours, comparés aux simples fréquences domicile / nul / extérieur.
    Coefficients ajustés sur les saisons précédentes seulement quand elles suffisent."""
    test = [m for m in rated if m["match_id"] in eld.current_ids]
    train = [m for m in eld.matches if m["match_id"] not in eld.current_ids]
    coefs = fit_outcome_model(train, eld.pre)
    hors_echantillon = coefs["ajuste"]
    if not hors_echantillon:
        coefs, train = eld.coefs, rated
    if not test or not train:
        return None
    base_n = {y: sum(1 for m in train if m["match_id"] in eld.pre and _outcome(m) == y) for y in (0, 1, 2)}
    tot = sum(base_n.values()) or 1
    base = {y: base_n[y] / tot for y in base_n}

    def scores(probs_of):
        ll = br = hit = 0.0
        for m in test:
            p = probs_of(m)
            y = _outcome(m)
            ll -= math.log(max(p[y], 1e-12))
            br += sum((p[k] - (1 if k == y else 0)) ** 2 for k in (0, 1, 2))
            hit += 1 if max((0, 1, 2), key=lambda k: p[k]) == y else 0
        n = len(test)
        return {"log_loss": round(ll / n, 4), "brier": round(br / n, 4), "reussite_pct": round(hit / n * 100, 1)}

    def model_probs(m):
        rh, ra, _ = eld.pre[m["match_id"]]
        ph, pn, pa = outcome_probs(rh - ra, coefs)
        return {0: pa, 1: pn, 2: ph}

    calib = {label: [0, 0.0, 0] for _, _, label in PROB_BUCKETS}   # matchs, proba moyenne, favori gagnant
    for m in test:
        p = model_probs(m)
        fav_side = 2 if p[2] >= p[0] else 0
        label = bucket_label(PROB_BUCKETS, p[fav_side] * 100)
        c = calib[label]
        c[0] += 1
        c[1] += p[fav_side]
        c[2] += 1 if _outcome(m) == fav_side else 0
    return {
        "matchs": len(test),
        "hors_echantillon": hors_echantillon,
        "modele": scores(model_probs),
        "reference": scores(lambda m: base),
        "calibration": [{"tranche": label, "matchs": c[0],
                         "prevu_pct": round(c[1] / c[0] * 100, 1) if c[0] else None,
                         "observe_pct": _pct(c[2], c[0])} for label, c in calib.items()],
    }
