"""Routes joueurs : classements, fiche joueur, forme récente."""
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from analytics import team_logos
from core import db
from fotmob_client import FOTMOB_LEAGUES, fetch_player_recent
from ingest import COMPETITION_META
from player_form import compute_fotmob_form, compute_recent_form
from player_scoring import analyze_player
from understat_client import UNDERSTAT_LEAGUES, fetch_player_matches

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Championnats disposant de statistiques individuelles (Understat + FotMob)
PLAYER_LEAGUES = set(UNDERSTAT_LEAGUES) | set(FOTMOB_LEAGUES)


async def top_players(team_id, code, limit=4, min_minutes=90):
    if team_id is None or code not in PLAYER_LEAGUES:
        return None
    docs = await db.players.find({"competition_code": code, "team_id": team_id,
                                  "minutes": {"$gte": min_minutes}}, {"_id": 0}).to_list(200)
    analyzed = [analyze_player(d) for d in docs]
    analyzed.sort(key=lambda p: p["scores"]["global"]["score"], reverse=True)
    return analyzed[:limit]


async def get_player_form(pid):
    """Forme récente d'un joueur, avec cache (18h) dans player_form.
    Understat pour les 5 grands championnats, FotMob pour Portugal/Pays-Bas."""
    # Joueurs connus uniquement : aucun appel externe pour un identifiant arbitraire.
    pdoc = await db.players.find_one({"player_id": pid}, {"_id": 0, "team_title": 1})
    if not pdoc:
        return None
    is_fm = str(pid).startswith("fm")
    doc = await db.player_form.find_one({"_id": pid})
    if doc:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(doc["updated_at"])
            if age < timedelta(hours=18):
                return doc.get("data")
        except Exception:  # noqa: BLE001
            pass
    try:
        if is_fm:
            recent = await fetch_player_recent(str(pid)[2:])
            data = compute_fotmob_form(recent)
        else:
            matches = await fetch_player_matches(pid)
            data = compute_recent_form(matches, pdoc.get("team_title"))
    except Exception as e:  # noqa: BLE001
        logger.error("Forme joueur %s échec: %s", pid, e)
        return doc.get("data") if doc else None
    if data:
        await db.player_form.update_one(
            {"_id": pid},
            {"$set": {"_id": pid, "updated_at": datetime.now(timezone.utc).isoformat(), "data": data}},
            upsert=True,
        )
    return data


@router.get("/leaderboard/players")
async def leaderboard_players(code: str | None = None, tri: str = "global",
                              poste: str | None = None, min_minutes: int | None = None):
    codes = [code] if code else list(PLAYER_LEAGUES)
    codes = [c for c in codes if c in PLAYER_LEAGUES]
    if not codes:
        return {"disponible": False,
                "message": "Statistiques joueurs indisponibles pour ce championnat."}
    mm = min_minutes if min_minutes is not None else (180 if tri == "global" else 30)
    docs = await db.players.find({"competition_code": {"$in": codes},
                                  "minutes": {"$gte": mm}}, {"_id": 0}).to_list(3000)
    if not docs:
        return {"disponible": False, "message": "Données joueurs pas encore synchronisées."}
    players = [analyze_player(d) for d in docs]
    logos = await team_logos(codes)
    for p, d in zip(players, docs):
        p["competition_nom"] = COMPETITION_META.get(d["competition_code"], {}).get("nom")
        p["team_logo"] = logos.get((d["competition_code"], d.get("team_id")))
    if poste and poste != "Tous":
        players = [p for p in players if p["poste"] == poste]
    if tri == "buteurs":
        players.sort(key=lambda p: (p["stats"]["buts"], p["stats"]["xG"]), reverse=True)
    elif tri == "passeurs":
        players.sort(key=lambda p: (p["stats"]["passes_decisives"], p["stats"]["xA"]), reverse=True)
    else:
        players.sort(key=lambda p: p["scores"]["global"]["score"], reverse=True)
    return {"disponible": True, "tri": tri, "min_minutes": mm, "joueurs": players[:100]}


@router.get("/player/{player_id}")
async def player(player_id: str):
    d = await db.players.find_one({"player_id": player_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Joueur introuvable")
    a = analyze_player(d)
    a["competition_nom"] = COMPETITION_META.get(d["competition_code"], {}).get("nom")
    a["team_logo"] = (await team_logos([d["competition_code"]])).get((d["competition_code"], d.get("team_id")))
    a["forme_recente"] = await get_player_form(player_id)
    return a


@router.post("/players/form")
async def players_form(payload: dict):
    ids = payload.get("ids") or []
    if not isinstance(ids, list):
        raise HTTPException(422, "« ids » doit être une liste d'identifiants de joueurs")
    # Understat : identifiant numérique ; FotMob : « fm » + numérique
    valid = list(dict.fromkeys(str(p) for p in ids if re.fullmatch(r"(fm)?\d{1,12}", str(p))))
    out = {}
    for pid in valid[:12]:
        data = await get_player_form(pid)
        if data:
            out[pid] = data
    return out
