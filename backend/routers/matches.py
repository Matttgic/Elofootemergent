"""Routes matchs et équipes : statut, compétitions, matchs du jour, détail d'un
match, fiche et classement des équipes, recherche, configuration de notation."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from analytics import calibration, compact, comp_data, match_summary, stats_analytics, team_logos
from core import db
from football_client import get_token
from ingest import COMPETITION_META, configured_codes, is_cup
from jobs import catch_up_if_stale, ingest_state
from player_scoring import analyze_player, player_scoring_config
from routers.players import PLAYER_LEAGUES, top_players
from scoring import paris_date, scoring_config
from signals import build_signals, h2h_insight, head_to_head
from understat_client import UNDERSTAT_LEAGUES

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/status")
async def status():
    rattrapage = await catch_up_if_stale()
    sync = await db.meta.find_one({"_id": "sync"}, {"_id": 0})
    nb = await db.matches.count_documents({})
    codes = configured_codes()
    # analyse quotidienne : 1 appel « matchs » par compétition + 1 « classement » par championnat
    daily = len(codes) + len([c for c in codes if not is_cup(c)])
    return {
        "token_present": bool(get_token()),
        "matchs_en_base": nb,
        "derniere_synchro": sync,
        "synchronisation_en_cours": ingest_state["running"] or rattrapage,
        "frequence": "Résultats rafraîchis chaque heure (1 appel API) · analyse complète 1×/jour",
        "quota": f"≈ 24 appels/jour pour les résultats + {daily} pour l'analyse quotidienne — "
                 "très en deçà de la limite gratuite (10/min)",
        "championnats": codes,
    }


@router.get("/competitions")
async def competitions():
    codes = configured_codes()
    counts = {}
    for c in codes:
        counts[c] = await db.matches.count_documents({"competition_code": c})
    return [
        {"code": c, "nom": COMPETITION_META[c]["nom"], "pays": COMPETITION_META[c]["pays"],
         "nb_matchs": counts.get(c, 0)}
        for c in codes
    ]


@router.get("/dates")
async def dates(code: str | None = None):
    q = {"competition_code": code} if code else {}
    ds = await db.matches.distinct("match_date", q)
    return sorted([d for d in ds if d])


@router.get("/matches")
async def matches(code: str | None = None, date: str | None = None):
    today = paris_date(datetime.now(timezone.utc).isoformat())
    target = date or today
    q = {"match_date": target}
    if code:
        q["competition_code"] = code
    docs = await db.matches.find(q, {"_id": 0}).sort("utc_date", 1).to_list(500)

    # regrouper par championnat pour ne charger chaque comp qu'une fois
    by_code = {}
    for d in docs:
        by_code.setdefault(d["competition_code"], []).append(d)

    out = []
    sd = await stats_analytics(None)
    for c, ms in by_code.items():
        comp = await comp_data(c)
        for m in ms:
            item = match_summary(m)
            item["competition"] = {"code": c, "nom": COMPETITION_META.get(c, {}).get("nom")}
            item["domicile"] = compact(comp.team((m.get("home_team") or {}).get("id")))
            item["exterieur"] = compact(comp.team((m.get("away_team") or {}).get("id")))
            dom, ext = item["domicile"], item["exterieur"]
            item["calibration"] = calibration(
                sd,
                dom["global"] if dom else None,
                ext["global"] if ext else None,
                dom["nom_court"] if dom else "Domicile",
                ext["nom_court"] if ext else "Extérieur",
            )
            out.append(item)
    out.sort(key=lambda x: x.get("utc_date") or "")
    return {"date": target, "matchs": out}


@router.get("/match/{match_id}")
async def match_detail(match_id: int):
    m = await db.matches.find_one({"match_id": match_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Match introuvable")
    code = m["competition_code"]
    comp = await comp_data(code)
    all_m = comp.matches
    hid = (m.get("home_team") or {}).get("id")
    aid = (m.get("away_team") or {}).get("id")
    home = comp.team(hid)
    away = comp.team(aid)

    avantages = None
    if home and away:
        def adv(k):
            hv = home[k]["score"] if home.get(k) else None
            av = away[k]["score"] if away.get(k) else None
            if hv is None or av is None:
                return {"gagnant": None, "ecart": None}
            if hv == av:
                return {"gagnant": "Égalité", "ecart": 0}
            return {"gagnant": home["nom_court"] if hv > av else away["nom_court"], "ecart": abs(hv - av)}
        avantages = {
            "global": adv("global"), "offensif": adv("offensif"),
            "defensif": adv("defensif"), "forme": adv("forme"),
        }

    if code in PLAYER_LEAGUES:
        dom_players = await top_players(hid, code)
        ext_players = await top_players(aid, code)
        src = "Understat · saison en cours" if code in UNDERSTAT_LEAGUES else "FotMob · saison en cours"
        joueurs = {"disponible": True,
                   "domicile": dom_players or [], "exterieur": ext_players or [],
                   "source": src}
    else:
        joueurs = {"disponible": False,
                   "message": f"Statistiques individuelles indisponibles pour {COMPETITION_META.get(code, {}).get('nom', code)} "
                              "avec les sources gratuites actuelles."}

    # Moyennes réelles du championnat pour calibrer l'estimation de buts
    finished = [(x.get("score") or {}).get("fullTime", {}) for x in all_m if x.get("status") == "FINISHED"]
    lg_home = [ft.get("home") for ft in finished if ft.get("home") is not None]
    lg_away = [ft.get("away") for ft in finished if ft.get("away") is not None]
    lg_home_avg = sum(lg_home) / len(lg_home) if lg_home else 1.45
    lg_away_avg = sum(lg_away) / len(lg_away) if lg_away else 1.15

    signaux = build_signals(all_m, hid, aid,
                            home["nom_court"] if home else "Domicile",
                            away["nom_court"] if away else "Extérieur",
                            lg_home_avg, lg_away_avg)
    confrontations = head_to_head(all_m, hid, aid)
    if signaux.get("disponible"):
        hi = h2h_insight(confrontations)
        if hi:
            signaux["signaux"].append(hi)

    # Indice de confiance (nombre de matchs analysés)
    hm = (home or {}).get("stats", {}).get("matchs_analyses", 0) if home else 0
    am = (away or {}).get("stats", {}).get("matchs_analyses", 0) if away else 0
    mn = min(hm, am)
    niveau = "Élevée" if mn >= 6 else ("Moyenne" if mn >= 4 else "Faible")
    fiabilite = {
        "niveau": niveau, "matchs_min": mn,
        "message": "Analyse fondée sur peu de matchs — à interpréter avec prudence." if mn < 4
                   else "Échantillon suffisant pour une lecture fiable." if mn >= 6
                   else "Échantillon modéré.",
    }

    # Calibration : lien écart de notes ↔ résultats observés historiquement
    cal = None
    if home and away and home.get("global") and away.get("global"):
        cal = calibration(await stats_analytics(None), home["global"]["score"], away["global"]["score"],
                          home["nom_court"], away["nom_court"])

    # Jours de repos (dernier match joué avant celui-ci)
    def _last_played(team_id):
        ds = [x["utc_date"] for x in all_m if x.get("status") == "FINISHED" and x.get("utc_date")
              and (m.get("utc_date") is None or x["utc_date"] < m["utc_date"])
              and team_id in ((x.get("home_team") or {}).get("id"), (x.get("away_team") or {}).get("id"))]
        return max(ds) if ds else None

    def _rest(team_id):
        last = _last_played(team_id)
        if not last or not m.get("utc_date"):
            return None
        d = (datetime.fromisoformat(m["utc_date"].replace("Z", "+00:00"))
             - datetime.fromisoformat(last.replace("Z", "+00:00"))).days
        return d if d >= 0 else None

    repos = {"domicile": _rest(hid), "exterieur": _rest(aid)}

    return {
        "match": {**match_summary(m),
                  "competition": {"code": code, "nom": COMPETITION_META.get(code, {}).get("nom"),
                                  "pays": COMPETITION_META.get(code, {}).get("pays")},
                  "home_team": m.get("home_team"), "away_team": m.get("away_team")},
        "domicile": home,
        "exterieur": away,
        "avantages": avantages,
        "fiabilite": fiabilite,
        "calibration": cal,
        "repos": repos,
        "signaux": signaux,
        "confrontations": confrontations,
        "joueurs": joueurs,
    }


@router.get("/team/{code}/{team_id}")
async def team(code: str, team_id: int):
    a = (await comp_data(code)).team(team_id)
    if not a:
        raise HTTPException(404, "Équipe introuvable ou sans match analysé")
    return a


@router.get("/leaderboard/teams")
async def leaderboard_teams(code: str | None = None):
    # « Tous » = championnats uniquement : les coupes dupliqueraient les clubs
    # (note calculée sur une autre compétition) et mêleraient des sélections nationales.
    codes = [code] if code else [c for c in configured_codes() if not is_cup(c)]
    result = []
    for c in codes:
        comp = await comp_data(c)
        for a in comp.analyses.values():
            if a and a.get("global"):
                row = compact(a)
                row["competition_code"] = c
                row["competition_nom"] = COMPETITION_META.get(c, {}).get("nom")
                result.append(row)
    result.sort(key=lambda x: (x.get("global") or 0), reverse=True)
    return result


@router.get("/search")
async def search(q: str = Query(..., min_length=2)):
    ql = q.lower()
    teams = []
    seen = set()
    for c in configured_codes():
        for tid, t in (await comp_data(c)).meta.items():
            if tid in seen:
                continue
            name = (t.get("name") or "") + " " + (t.get("shortName") or "")
            if ql in name.lower():
                seen.add(tid)
                teams.append({"team_id": tid, "nom": t.get("name"),
                              "nom_court": t.get("shortName"), "logo": t.get("crest"),
                              "competition_code": c,
                              "competition_nom": COMPETITION_META.get(c, {}).get("nom")})
    # joueurs correspondants (Understat + FotMob)
    pdocs = await db.players.find({"nom": {"$regex": re.escape(q), "$options": "i"}}, {"_id": 0}).to_list(60)
    pdocs.sort(key=lambda d: d.get("minutes", 0), reverse=True)
    joueurs = []
    logos = await team_logos(d["competition_code"] for d in pdocs[:20])
    for d in pdocs[:20]:
        a = analyze_player(d)
        joueurs.append({"player_id": a["player_id"], "nom": a["nom"], "poste": a["poste"],
                        "team_title": a["team_title"], "competition_code": d["competition_code"],
                        "team_logo": logos.get((d["competition_code"], d.get("team_id"))),
                        "competition_nom": COMPETITION_META.get(d["competition_code"], {}).get("nom"),
                        "score": a["scores"]["global"]["score"]})
    message = None if joueurs else ("Aucun joueur trouvé (couverture : 5 grands championnats "
                                    "+ Portugal et Pays-Bas).")
    return {"equipes": teams[:30],
            "joueurs": {"disponible": bool(joueurs), "resultats": joueurs, "message": message}}


@router.get("/scoring/config")
async def scoring_conf():
    return {"equipes": scoring_config(), "joueurs": player_scoring_config()}
