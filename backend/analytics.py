"""Données et calculs partagés par les routes : chargement d'un championnat avec
ses analyses d'équipes, statistiques de calibration, et leur cache.

Les analyses sont calculées une fois par championnat puis gardées en mémoire
(CACHE_TTL, et vidées après chaque ingestion via `invalidate_caches`) au lieu
d'être recalculées à chaque requête. Les calculs lourds tournent dans un thread
pour ne pas bloquer la boucle asynchrone ; un verrou par clé évite qu'une
expiration de cache déclenche le même calcul en parallèle.
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from core import db
from ingest import configured_codes, is_cup
from scoring import MIN_HISTORY, analyze_team, pre_match_ratings

STAT_BUCKETS = [(0, 5, "0–5"), (5, 10, "5–10"), (10, 15, "10–15"), (15, 20, "15–20"),
                (20, 25, "20–25"), (25, 30, "25–30"), (30, 35, "30–35"), (35, 40, "35–40"),
                (40, 45, "40–45"), (45, 50, "45–50"), (50, 999, "50+")]

CACHE_TTL = timedelta(minutes=10)
_comp_cache = {}                  # code -> (horodatage, CompData)
_stats_cache = {}                 # code | "ALL" -> (horodatage, dict)
_locks = defaultdict(asyncio.Lock)
_generation = 0                   # incrémenté à chaque invalidation


def invalidate_caches():
    """À appeler après une ingestion : les prochaines requêtes relisent la base."""
    global _generation
    _generation += 1
    _comp_cache.clear()
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


def calibration(sd, home_score, away_score, home_name, away_name):
    """Indicateur rapide : écart de notes + % de victoire du favori observé
    historiquement pour cette tranche d'écart (statistiques descriptives)."""
    if home_score is None or away_score is None:
        return None
    gap = abs(home_score - away_score)
    fav = home_name if home_score >= away_score else away_name
    fav_cote = "domicile" if home_score >= away_score else "exterieur"
    for lo, hi, label in STAT_BUCKETS:
        if lo <= gap < hi:
            b = next((x for x in sd.get("par_ecart_note", []) if x["tranche"] == label), None)
            if b and b.get("matchs"):
                sf = b.get("scores_frequents") or []
                top = sf[0] if sf else None
                fav_pct = b["note_sup_gagne_pct"]
                value = bool(top and b["matchs"] >= 10 and fav_pct >= 68 and top["pct"] >= 20)
                return {"ecart": gap, "tranche": label, "favori": fav, "favori_cote": fav_cote,
                        "favori_gagne_pct": fav_pct, "nul_pct": b["nul_pct"],
                        "outsider_gagne_pct": b["note_inf_gagne_pct"], "echantillon": b["matchs"],
                        "score_frequent": top, "value": value}
            return None
    return None


async def stats_analytics(code=None):
    """Statistiques descriptives : lien entre l'écart de notes et le résultat réel.
    Chaque match terminé est comparé aux notes que les équipes avaient AVANT son
    coup d'envoi (matchs antérieurs uniquement), jamais aux notes actuelles."""
    async def load():
        codes = [c for c in ([code] if code else configured_codes()) if not is_cup(c)]
        match_lists = [(await comp_data(c)).matches for c in codes]
        return await asyncio.to_thread(_compute_stats, match_lists)
    return await _cached(_stats_cache, code or "ALL", load)


def _compute_stats(match_lists):
    higher = {"V": 0, "N": 0, "D": 0}          # résultat de l'équipe la mieux notée
    home_out = {"V": 0, "N": 0, "D": 0}        # résultat du point de vue domicile
    buckets = {b[2]: {"note_sup": 0, "nul": 0, "note_inf": 0} for b in STAT_BUCKETS}
    scores_par_ecart = {b[2]: {} for b in STAT_BUCKETS}
    total = 0
    home_total = 0

    for all_m in match_lists:
        ratings = pre_match_ratings(all_m)   # {match_id: (note_dom, note_ext)} avant-match
        for m in all_m:
            if m.get("status") != "FINISHED":
                continue
            ft = (m.get("score") or {}).get("fullTime") or {}
            gh, ga = ft.get("home"), ft.get("away")
            if gh is None or ga is None:
                continue
            home_total += 1
            home_out["V" if gh > ga else ("N" if gh == ga else "D")] += 1
            if m.get("match_id") not in ratings:
                continue
            total += 1
            rh, raw = ratings[m["match_id"]]
            if rh == raw:
                continue
            diff = abs(rh - raw)
            sup_is_home = rh > raw
            if gh == ga:
                res = "N"
            elif (gh > ga) == sup_is_home:
                res = "V"   # l'équipe mieux notée a gagné
            else:
                res = "D"   # l'équipe mieux notée a perdu
            higher[res] += 1
            for lo, hi, label in STAT_BUCKETS:
                if lo <= diff < hi:
                    key = "note_sup" if res == "V" else ("nul" if res == "N" else "note_inf")
                    buckets[label][key] += 1
                    sg, ig = (gh, ga) if sup_is_home else (ga, gh)
                    sk = f"{sg}-{ig}"   # score du point de vue de l'équipe la mieux notée
                    scores_par_ecart[label][sk] = scores_par_ecart[label].get(sk, 0) + 1
                    break

    def pct(part, whole):
        return round(part / whole * 100, 1) if whole else None

    h_total = sum(higher.values())
    par_ecart = []
    for _, _, label in STAT_BUCKETS:
        b = buckets[label]
        n = b["note_sup"] + b["nul"] + b["note_inf"]
        sc = scores_par_ecart[label]
        tot_sc = sum(sc.values())
        freq = sorted(sc.items(), key=lambda x: (x[1], x[0]), reverse=True)[:4]
        scores_frequents = [{"score": k, "pct": pct(v, tot_sc), "n": v} for k, v in freq]
        par_ecart.append({
            "tranche": label, "matchs": n,
            "note_sup_gagne_pct": pct(b["note_sup"], n),
            "nul_pct": pct(b["nul"], n),
            "note_inf_gagne_pct": pct(b["note_inf"], n),
            "scores_frequents": scores_frequents,
        })

    return {
        "disponible": total > 0,
        "echantillon": total,
        "note_superieure": {
            "victoires_pct": pct(higher["V"], h_total),
            "nuls_pct": pct(higher["N"], h_total),
            "defaites_pct": pct(higher["D"], h_total),
        },
        "avantage_domicile": {
            "domicile_pct": pct(home_out["V"], home_total),
            "nul_pct": pct(home_out["N"], home_total),
            "exterieur_pct": pct(home_out["D"], home_total),
        },
        "par_ecart_note": par_ecart,
        "note": "Statistiques descriptives : chaque match terminé est comparé aux notes que les deux "
                "équipes avaient avant le coup d'envoi (calculées uniquement sur les matchs antérieurs, "
                f"au moins {MIN_HISTORY} chacune). Championnats uniquement, hors coupes.",
    }
