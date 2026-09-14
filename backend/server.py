from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
import re
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

from scoring import analyze_team, scoring_config, paris_date
from signals import build_signals, head_to_head
from player_scoring import analyze_player, player_scoring_config
from player_form import compute_recent_form
from understat_client import UNDERSTAT_LEAGUES, fetch_player_matches
from ingest import run_ingest, run_light_ingest, configured_codes, COMPETITION_META, is_cup
from football_client import get_token

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="FootPulse Analytics API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

# État de synchronisation (évite les ingestions concurrentes manuel/planifié)
ingest_state = {"running": False, "started_at": None}


async def _guarded(factory):
    if ingest_state["running"]:
        logger.info("Ingestion déjà en cours — appel ignoré.")
        return {"ok": False, "raison": "deja_en_cours"}
    ingest_state["running"] = True
    ingest_state["started_at"] = datetime.now(timezone.utc).isoformat()
    try:
        return await factory()
    finally:
        ingest_state["running"] = False


async def run_full_guarded():
    return await _guarded(lambda: run_ingest(db))


async def run_light_guarded():
    return await _guarded(lambda: run_light_ingest(db))


# ---------------------------------------------------------------------------
# Helpers de chargement / analyse
# ---------------------------------------------------------------------------
async def _load_comp(code):
    matches = await db.matches.find({"competition_code": code}, {"_id": 0}).to_list(2000)
    standings = await db.standings.find_one({"competition_code": code}, {"_id": 0})
    pos_map, rows, total = {}, {}, 0
    if standings and standings.get("table"):
        table = standings["table"]
        total = len(table)
        for entry in table:
            tid = (entry.get("team") or {}).get("id")
            if tid is None:
                continue
            pos_map[tid] = (entry.get("position"), total)
            rows[tid] = {
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
    meta = {}
    for m in matches:
        for side in ("home_team", "away_team"):
            t = m.get(side) or {}
            if t.get("id") is not None:
                meta[t["id"]] = t
    return matches, pos_map, rows, meta


def _analyze(matches, pos_map, rows, meta, team_id):
    return analyze_team(matches, pos_map, team_id, meta.get(team_id), rows.get(team_id))


def _compact(analysis):
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


def _match_summary(m):
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


async def _top_players(team_id, code, limit=4, min_minutes=90):
    if team_id is None or code not in UNDERSTAT_LEAGUES:
        return None
    docs = await db.players.find({"competition_code": code, "team_id": team_id,
                                  "minutes": {"$gte": min_minutes}}, {"_id": 0}).to_list(200)
    analyzed = [analyze_player(d) for d in docs]
    analyzed.sort(key=lambda p: p["scores"]["global"]["score"], reverse=True)
    return analyzed[:limit]


async def get_player_form(pid):
    """Forme récente d'un joueur, avec cache (18h) dans player_form."""
    from datetime import timedelta
    doc = await db.player_form.find_one({"_id": pid})
    if doc:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(doc["updated_at"])
            if age < timedelta(hours=18):
                return doc.get("data")
        except Exception:  # noqa: BLE001
            pass
    pdoc = await db.players.find_one({"player_id": pid}, {"_id": 0, "team_title": 1})
    if not pdoc:
        return doc.get("data") if doc else None
    try:
        matches = await fetch_player_matches(pid)
        data = compute_recent_form(matches, pdoc.get("team_title"))
    except Exception as e:  # noqa: BLE001
        logger.error("Forme joueur %s échec: %s", pid, e)
        return doc.get("data") if doc else None
    await db.player_form.update_one(
        {"_id": pid},
        {"$set": {"_id": pid, "updated_at": datetime.now(timezone.utc).isoformat(), "data": data}},
        upsert=True,
    )
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@api_router.get("/health")
async def health():
    return {"ok": True}


@api_router.get("/status")
async def status():
    sync = await db.meta.find_one({"_id": "sync"}, {"_id": 0})
    nb = await db.matches.count_documents({})
    return {
        "token_present": bool(get_token()),
        "matchs_en_base": nb,
        "derniere_synchro": sync,
        "synchronisation_en_cours": ingest_state["running"],
        "frequence": "Résultats rafraîchis chaque heure (1 appel API) · analyse complète 1×/jour",
        "quota": "≈ 24 appels/jour pour les résultats + 14 pour l'analyse quotidienne — très en deçà de la limite gratuite (10/min)",
        "championnats": configured_codes(),
    }


@api_router.get("/competitions")
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


@api_router.get("/dates")
async def dates(code: str | None = None):
    q = {"competition_code": code} if code else {}
    ds = await db.matches.distinct("match_date", q)
    return sorted([d for d in ds if d])


@api_router.get("/matches")
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
    for c, ms in by_code.items():
        all_m, pos_map, rows, meta = await _load_comp(c)
        for m in ms:
            hid = (m.get("home_team") or {}).get("id")
            aid = (m.get("away_team") or {}).get("id")
            item = _match_summary(m)
            item["competition"] = {"code": c, "nom": COMPETITION_META.get(c, {}).get("nom")}
            item["domicile"] = _compact(_analyze(all_m, pos_map, rows, meta, hid))
            item["exterieur"] = _compact(_analyze(all_m, pos_map, rows, meta, aid))
            out.append(item)
    out.sort(key=lambda x: x.get("utc_date") or "")
    return {"date": target, "matchs": out}


@api_router.get("/match/{match_id}")
async def match_detail(match_id: int):
    m = await db.matches.find_one({"match_id": match_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Match introuvable")
    code = m["competition_code"]
    all_m, pos_map, rows, meta = await _load_comp(code)
    hid = (m.get("home_team") or {}).get("id")
    aid = (m.get("away_team") or {}).get("id")
    home = _analyze(all_m, pos_map, rows, meta, hid)
    away = _analyze(all_m, pos_map, rows, meta, aid)

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

    covered = code in UNDERSTAT_LEAGUES
    if covered:
        dom_players = await _top_players(hid, code)
        ext_players = await _top_players(aid, code)
        joueurs = {"disponible": True,
                   "domicile": dom_players or [], "exterieur": ext_players or [],
                   "source": "Understat · saison en cours"}
    else:
        joueurs = {"disponible": False,
                   "message": f"Statistiques individuelles indisponibles pour {COMPETITION_META.get(code, {}).get('nom', code)} "
                              "avec les sources gratuites actuelles."}

    # Moyennes réelles du championnat pour calibrer l'estimation de buts
    lg_home = [ (m.get("score") or {}).get("fullTime", {}).get("home")
                for m in all_m if m.get("status") == "FINISHED" ]
    lg_away = [ (m.get("score") or {}).get("fullTime", {}).get("away")
                for m in all_m if m.get("status") == "FINISHED" ]
    lg_home = [g for g in lg_home if g is not None]
    lg_away = [g for g in lg_away if g is not None]
    lg_home_avg = sum(lg_home) / len(lg_home) if lg_home else 1.45
    lg_away_avg = sum(lg_away) / len(lg_away) if lg_away else 1.15

    return {
        "match": {**_match_summary(m),
                  "competition": {"code": code, "nom": COMPETITION_META.get(code, {}).get("nom"),
                                  "pays": COMPETITION_META.get(code, {}).get("pays")},
                  "home_team": m.get("home_team"), "away_team": m.get("away_team")},
        "domicile": home,
        "exterieur": away,
        "avantages": avantages,
        "signaux": build_signals(all_m, hid, aid,
                                 home["nom_court"] if home else "Domicile",
                                 away["nom_court"] if away else "Extérieur",
                                 lg_home_avg, lg_away_avg),
        "confrontations": head_to_head(all_m, hid, aid),
        "joueurs": joueurs,
    }


@api_router.get("/team/{code}/{team_id}")
async def team(code: str, team_id: int):
    all_m, pos_map, rows, meta = await _load_comp(code)
    a = _analyze(all_m, pos_map, rows, meta, team_id)
    if not a:
        raise HTTPException(404, "Équipe introuvable ou sans match analysé")
    return a


@api_router.get("/leaderboard/teams")
async def leaderboard_teams(code: str | None = None):
    codes = [code] if code else configured_codes()
    result = []
    for c in codes:
        all_m, pos_map, rows, meta = await _load_comp(c)
        for tid in meta:
            a = _analyze(all_m, pos_map, rows, meta, tid)
            if a and a.get("global"):
                comp = _compact(a)
                comp["competition_code"] = c
                comp["competition_nom"] = COMPETITION_META.get(c, {}).get("nom")
                result.append(comp)
    result.sort(key=lambda x: (x.get("global") or 0), reverse=True)
    return result


@api_router.get("/leaderboard/players")
async def leaderboard_players(code: str | None = None, tri: str = "global",
                              min_minutes: int | None = None):
    codes = [code] if code else list(UNDERSTAT_LEAGUES.keys())
    codes = [c for c in codes if c in UNDERSTAT_LEAGUES]
    if not codes:
        return {"disponible": False,
                "message": "Statistiques joueurs indisponibles pour ce championnat."}
    mm = min_minutes if min_minutes is not None else (180 if tri == "global" else 30)
    docs = await db.players.find({"competition_code": {"$in": codes},
                                  "minutes": {"$gte": mm}}, {"_id": 0}).to_list(3000)
    if not docs:
        return {"disponible": False, "message": "Données joueurs pas encore synchronisées."}
    players = [analyze_player(d) for d in docs]
    for p, d in zip(players, docs):
        p["competition_nom"] = COMPETITION_META.get(d["competition_code"], {}).get("nom")
    if tri == "buteurs":
        players.sort(key=lambda p: (p["stats"]["buts"], p["stats"]["xG"]), reverse=True)
    elif tri == "passeurs":
        players.sort(key=lambda p: (p["stats"]["passes_decisives"], p["stats"]["xA"]), reverse=True)
    else:
        players.sort(key=lambda p: p["scores"]["global"]["score"], reverse=True)
    return {"disponible": True, "tri": tri, "min_minutes": mm, "joueurs": players[:100]}


@api_router.get("/player/{player_id}")
async def player(player_id: str):
    d = await db.players.find_one({"player_id": player_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Joueur introuvable")
    a = analyze_player(d)
    a["competition_nom"] = COMPETITION_META.get(d["competition_code"], {}).get("nom")
    a["forme_recente"] = await get_player_form(player_id)
    return a


@api_router.post("/players/form")
async def players_form(payload: dict):
    ids = payload.get("ids") or []
    out = {}
    for pid in ids[:12]:
        data = await get_player_form(str(pid))
        if data:
            out[str(pid)] = data
    return out


@api_router.get("/search")
async def search(q: str = Query(..., min_length=2)):
    ql = q.lower()
    teams = []
    seen = set()
    for c in configured_codes():
        docs = await db.matches.find({"competition_code": c}, {"_id": 0, "home_team": 1, "away_team": 1}).to_list(2000)
        for d in docs:
            for side in ("home_team", "away_team"):
                t = d.get(side) or {}
                tid = t.get("id")
                if tid is None or tid in seen:
                    continue
                name = (t.get("name") or "") + " " + (t.get("shortName") or "")
                if ql in name.lower():
                    seen.add(tid)
                    teams.append({"team_id": tid, "nom": t.get("name"),
                                  "nom_court": t.get("shortName"), "logo": t.get("crest"),
                                  "competition_code": c,
                                  "competition_nom": COMPETITION_META.get(c, {}).get("nom")})
    # joueurs correspondants (Understat)
    pdocs = await db.players.find({"nom": {"$regex": re.escape(q), "$options": "i"}}, {"_id": 0}).to_list(60)
    pdocs.sort(key=lambda d: d.get("minutes", 0), reverse=True)
    joueurs = []
    for d in pdocs[:20]:
        a = analyze_player(d)
        joueurs.append({"player_id": a["player_id"], "nom": a["nom"], "poste": a["poste"],
                        "team_title": a["team_title"], "competition_code": d["competition_code"],
                        "competition_nom": COMPETITION_META.get(d["competition_code"], {}).get("nom"),
                        "score": a["scores"]["global"]["score"]})
    return {"equipes": teams[:30],
            "joueurs": {"disponible": bool(joueurs), "resultats": joueurs,
                        "message": None if joueurs else "Aucun joueur trouvé (couverture : 5 grands championnats)."}}


@api_router.get("/scoring/config")
async def scoring_conf():
    return {"equipes": scoring_config(), "joueurs": player_scoring_config()}


STAT_BUCKETS = [(0, 5, "0–5"), (5, 10, "5–10"), (10, 15, "10–15"), (15, 20, "15–20"),
                (20, 25, "20–25"), (25, 30, "25–30"), (30, 999, "30+")]
_stats_cache = {}  # code -> (timestamp, data), TTL 10 min


@api_router.get("/stats")
async def stats_analytics(code: str | None = None):
    """Statistiques descriptives : lien entre l'écart de notes et le résultat réel.
    Fondé sur les matchs terminés et les notes actuelles des équipes."""
    from datetime import timedelta
    ck = code or "ALL"
    cached = _stats_cache.get(ck)
    if cached and (datetime.now(timezone.utc) - cached[0]) < timedelta(minutes=10):
        return cached[1]
    codes = [code] if code else [c for c in configured_codes() if not is_cup(c)]
    codes = [c for c in codes if not is_cup(c)]
    higher = {"V": 0, "N": 0, "D": 0}          # résultat de l'équipe la mieux notée
    home_out = {"V": 0, "N": 0, "D": 0}        # résultat du point de vue domicile
    buckets = {b[2]: {"note_sup": 0, "nul": 0, "note_inf": 0} for b in STAT_BUCKETS}
    total = 0

    for c in codes:
        all_m, pos_map, rows, meta = await _load_comp(c)
        ratings = {}
        for tid in meta:
            a = _analyze(all_m, pos_map, rows, meta, tid)
            if a and a.get("global"):
                ratings[tid] = a["global"]["score"]
        for m in all_m:
            if m.get("status") != "FINISHED":
                continue
            ft = (m.get("score") or {}).get("fullTime") or {}
            gh, ga = ft.get("home"), ft.get("away")
            hid = (m.get("home_team") or {}).get("id")
            aid = (m.get("away_team") or {}).get("id")
            if gh is None or ga is None or hid not in ratings or aid not in ratings:
                continue
            total += 1
            home_out["V" if gh > ga else ("N" if gh == ga else "D")] += 1
            rh, raw = ratings[hid], ratings[aid]
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
                    break

    def pct(part, whole):
        return round(part / whole * 100, 1) if whole else None

    h_total = sum(higher.values())
    par_ecart = []
    for _, _, label in STAT_BUCKETS:
        b = buckets[label]
        n = b["note_sup"] + b["nul"] + b["note_inf"]
        par_ecart.append({
            "tranche": label, "matchs": n,
            "note_sup_gagne_pct": pct(b["note_sup"], n),
            "nul_pct": pct(b["nul"], n),
            "note_inf_gagne_pct": pct(b["note_inf"], n),
        })

    result = {
        "disponible": total > 0,
        "echantillon": total,
        "note_superieure": {
            "victoires_pct": pct(higher["V"], h_total),
            "nuls_pct": pct(higher["N"], h_total),
            "defaites_pct": pct(higher["D"], h_total),
        },
        "avantage_domicile": {
            "domicile_pct": pct(home_out["V"], total),
            "nul_pct": pct(home_out["N"], total),
            "exterieur_pct": pct(home_out["D"], total),
        },
        "par_ecart_note": par_ecart,
        "note": "Statistiques descriptives fondées sur les matchs terminés et les notes actuelles "
                "des équipes (5 grands championnats et autres ligues, hors coupes).",
    }
    _stats_cache[ck] = (datetime.now(timezone.utc), result)
    return result


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _startup_ingest():
    await db.matches.create_index("match_id", unique=True)
    await db.matches.create_index([("competition_code", 1), ("match_date", 1)])
    await db.standings.create_index("competition_code", unique=True)
    await db.players.create_index([("competition_code", 1), ("team_id", 1)])
    await db.players.create_index("player_id")
    if not get_token():
        return
    from datetime import timedelta
    nb = await db.matches.count_documents({})
    stale = True
    sync = await db.meta.find_one({"_id": "sync"})
    if sync and sync.get("last_sync"):
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(sync["last_sync"])
            stale = age > timedelta(hours=3)
        except Exception:  # noqa: BLE001
            stale = True
    if nb == 0:
        logger.info("Base vide — analyse complète en arrière-plan.")
        asyncio.create_task(run_full_guarded())
    elif stale:
        logger.info("Données périmées — rafraîchissement léger de rattrapage.")
        asyncio.create_task(run_light_guarded())


@app.on_event("startup")
async def on_startup():
    await _startup_ingest()
    # Rafraîchissement léger fréquent (1 appel API) pour les résultats + notes
    scheduler.add_job(run_light_guarded, "cron", minute=5,
                      id="light", replace_existing=True, max_instances=1, coalesce=True)
    # Analyse complète 1×/jour (saison + classements + joueurs)
    scheduler.add_job(run_full_guarded, "cron", hour=4, minute=30,
                      id="full", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)
    client.close()
