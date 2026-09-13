from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

from scoring import analyze_team, scoring_config, paris_date
from signals import build_signals, head_to_head
from ingest import run_ingest, configured_codes, COMPETITION_META
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
                                 away["nom_court"] if away else "Extérieur"),
        "confrontations": head_to_head(all_m, hid, aid),
        "joueurs": {"disponible": False,
                    "message": "Statistiques individuelles des joueurs indisponibles avec la source gratuite actuelle."},
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
async def leaderboard_players():
    return {"disponible": False,
            "message": "Le classement des joueurs nécessite des statistiques individuelles, "
                       "indisponibles avec la source de données gratuite actuelle."}


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
    return {"equipes": teams[:30],
            "joueurs": {"disponible": False,
                        "message": "Recherche de joueurs indisponible (pas de données individuelles gratuites)."}}


@api_router.get("/scoring/config")
async def scoring_conf():
    return scoring_config()


@api_router.post("/admin/ingest")
async def admin_ingest():
    return await run_ingest(db)


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
    if get_token():
        nb = await db.matches.count_documents({})
        if nb == 0:
            logger.info("Base vide — ingestion initiale lancée en arrière-plan.")
            asyncio.create_task(run_ingest(db))


@app.on_event("startup")
async def on_startup():
    await _startup_ingest()
    scheduler.add_job(run_ingest, "cron", args=[db], hour=4, minute=10,
                      id="daily-ingest", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)
    client.close()
