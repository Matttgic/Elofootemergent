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

from scoring import analyze_team, scoring_config, paris_date, pre_match_ratings, MIN_HISTORY
from signals import build_signals, head_to_head, h2h_insight
from betting import MODELE_PARIS, match_fixture, kelly_fraction, simulate
from player_scoring import analyze_player, player_scoring_config
from player_form import compute_recent_form, compute_fotmob_form
from understat_client import UNDERSTAT_LEAGUES, fetch_player_matches
from fotmob_client import FOTMOB_LEAGUES, fetch_player_recent
from odds_client import fetch_odds, ODDS_SPORT
from ingest import run_ingest, run_light_ingest, configured_codes, COMPETITION_META, is_cup
from football_client import get_token

# Championnats disposant de statistiques individuelles (Understat + FotMob)
PLAYER_LEAGUES = set(UNDERSTAT_LEAGUES) | set(FOTMOB_LEAGUES)

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
    res = await _guarded(lambda: run_ingest(db))
    try:
        await settle_bets()
        await snapshot_bets()
    except Exception as e:  # noqa: BLE001
        logger.error("Simulation paris (full) échec: %s", e)
    return res


async def run_light_guarded():
    res = await _guarded(lambda: run_light_ingest(db))
    try:
        await settle_bets()
    except Exception as e:  # noqa: BLE001
        logger.error("Règlement paris (light) échec: %s", e)
    return res


# ---------------------------------------------------------------------------
# Simulation de paris (cotes réelles The Odds API — stratégies Favori & Value)
# ---------------------------------------------------------------------------
async def snapshot_bets():
    """Fige un pari (cote favori + écart de notes) pour chaque match à venir dont
    on obtient les vraies cotes. Idempotent (un pari par match) ; un pari figé
    avec un ancien modèle et encore en attente est remplacé."""
    if not os.environ.get("ODDS_API_KEY"):
        return {"ok": False, "raison": "cle_absente"}
    sd = await stats_analytics(None)
    created = 0
    for code, sport in ODDS_SPORT.items():
        try:
            fixtures = await fetch_odds(sport)
        except Exception as e:  # noqa: BLE001
            logger.error("Cotes %s échec: %s", code, e)
            continue
        if not fixtures:
            continue
        all_m, pos_map, rows, meta = await _load_comp(code)
        upcoming = [m for m in all_m if m.get("status") in ("TIMED", "SCHEDULED", "POSTPONED")]
        for fx in fixtures:
            if not (fx.get("home_odds") and fx.get("away_odds")):
                continue
            m = match_fixture(fx, upcoming)
            if not m:
                continue
            mid = m["match_id"]
            existing = await db.bets.find_one({"_id": mid}, {"modele": 1})
            if existing and (existing.get("modele") or 0) >= MODELE_PARIS:
                continue
            hid = (m.get("home_team") or {}).get("id")
            aid = (m.get("away_team") or {}).get("id")
            home = _analyze(all_m, pos_map, rows, meta, hid)
            away = _analyze(all_m, pos_map, rows, meta, aid)
            if not (home and away and home.get("global") and away.get("global")):
                continue
            cal = _calibration(sd, home["global"]["score"], away["global"]["score"],
                               home["nom_court"], away["nom_court"])
            if not cal:
                continue
            fav_side = "home" if cal["favori_cote"] == "domicile" else "away"
            fav_odds = fx["home_odds"] if fav_side == "home" else fx["away_odds"]
            if not fav_odds or fav_odds <= 1:
                continue
            p = cal["favori_gagne_pct"] / 100.0
            implied = 1.0 / fav_odds
            await db.bets.replace_one({"_id": mid}, {
                "_id": mid, "modele": MODELE_PARIS,
                "competition_code": code, "ecart": cal["ecart"], "tranche": cal["tranche"],
                "fav_side": fav_side, "fav_nom": cal["favori"], "fav_odds": round(fav_odds, 3),
                "home_odds": fx["home_odds"], "draw_odds": fx["draw_odds"], "away_odds": fx["away_odds"],
                "bookmaker": fx["bookmaker"], "model_prob": round(p, 4), "implied_prob": round(implied, 4),
                "is_value": p > implied, "kelly_f": round(kelly_fraction(p, fav_odds), 4),
                "commence_time": fx["commence_time"],
                "snapshot_at": datetime.now(timezone.utc).isoformat(), "status": "pending",
            }, upsert=True)
            created += 1
    logger.info("Paris figés (snapshot) : %s nouveaux", created)
    return {"ok": True, "crees": created}


async def settle_bets():
    """Règle les paris en attente dont le match est terminé (aucun appel API)."""
    pending = await db.bets.find({"status": "pending"}).to_list(2000)
    settled = 0
    for bet in pending:
        m = await db.matches.find_one({"match_id": bet["_id"]}, {"_id": 0, "status": 1, "score": 1})
        if not m or m.get("status") != "FINISHED":
            continue
        ft = (m.get("score") or {}).get("fullTime") or {}
        h, a = ft.get("home"), ft.get("away")
        if h is None or a is None:
            continue
        result = "home" if h > a else ("away" if a > h else "draw")
        won = result == bet["fav_side"]
        await db.bets.update_one({"_id": bet["_id"]},
                                 {"$set": {"status": "won" if won else "lost", "resultat": result,
                                           "settled_at": datetime.now(timezone.utc).isoformat()}})
        settled += 1
    if settled:
        logger.info("Paris réglés : %s", settled)
    return settled


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


def _calibration(sd, home_score, away_score, home_name, away_name):
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


async def _top_players(team_id, code, limit=4, min_minutes=90):
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
    from datetime import timedelta
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
    sd = await stats_analytics(None)
    for c, ms in by_code.items():
        all_m, pos_map, rows, meta = await _load_comp(c)
        for m in ms:
            hid = (m.get("home_team") or {}).get("id")
            aid = (m.get("away_team") or {}).get("id")
            item = _match_summary(m)
            item["competition"] = {"code": c, "nom": COMPETITION_META.get(c, {}).get("nom")}
            item["domicile"] = _compact(_analyze(all_m, pos_map, rows, meta, hid))
            item["exterieur"] = _compact(_analyze(all_m, pos_map, rows, meta, aid))
            dom, ext = item["domicile"], item["exterieur"]
            item["calibration"] = _calibration(
                sd,
                dom["global"] if dom else None,
                ext["global"] if ext else None,
                dom["nom_court"] if dom else "Domicile",
                ext["nom_court"] if ext else "Extérieur",
            )
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

    covered = code in PLAYER_LEAGUES
    if covered:
        dom_players = await _top_players(hid, code)
        ext_players = await _top_players(aid, code)
        src = "Understat · saison en cours" if code in UNDERSTAT_LEAGUES else "FotMob · saison en cours"
        joueurs = {"disponible": True,
                   "domicile": dom_players or [], "exterieur": ext_players or [],
                   "source": src}
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
    calibration = None
    if home and away and home.get("global") and away.get("global"):
        gap = abs(home["global"]["score"] - away["global"]["score"])
        fav = home["nom_court"] if home["global"]["score"] >= away["global"]["score"] else away["nom_court"]
        sd = await stats_analytics(None)
        for lo, hi, label in STAT_BUCKETS:
            if lo <= gap < hi:
                b = next((x for x in sd.get("par_ecart_note", []) if x["tranche"] == label), None)
                if b and b.get("matchs"):
                    calibration = {"ecart": gap, "tranche": label, "favori": fav,
                                   "favori_gagne_pct": b["note_sup_gagne_pct"], "nul_pct": b["nul_pct"],
                                   "outsider_gagne_pct": b["note_inf_gagne_pct"], "echantillon": b["matchs"]}
                break

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
        "match": {**_match_summary(m),
                  "competition": {"code": code, "nom": COMPETITION_META.get(code, {}).get("nom"),
                                  "pays": COMPETITION_META.get(code, {}).get("pays")},
                  "home_team": m.get("home_team"), "away_team": m.get("away_team")},
        "domicile": home,
        "exterieur": away,
        "avantages": avantages,
        "fiabilite": fiabilite,
        "calibration": calibration,
        "repos": repos,
        "signaux": signaux,
        "confrontations": confrontations,
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
    for p, d in zip(players, docs):
        p["competition_nom"] = COMPETITION_META.get(d["competition_code"], {}).get("nom")
    if poste and poste != "Tous":
        players = [p for p in players if p["poste"] == poste]
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
                        "message": None if joueurs else "Aucun joueur trouvé (couverture : 5 grands championnats + Portugal et Pays-Bas)."}}


@api_router.get("/scoring/config")
async def scoring_conf():
    return {"equipes": scoring_config(), "joueurs": player_scoring_config()}


STAT_BUCKETS = [(0, 5, "0–5"), (5, 10, "5–10"), (10, 15, "10–15"), (15, 20, "15–20"),
                (20, 25, "20–25"), (25, 30, "25–30"), (30, 35, "30–35"), (35, 40, "35–40"),
                (40, 45, "40–45"), (45, 50, "45–50"), (50, 999, "50+")]
_stats_cache = {}  # code -> (timestamp, data), TTL 10 min


@api_router.get("/stats")
async def stats_analytics(code: str | None = None):
    """Statistiques descriptives : lien entre l'écart de notes et le résultat réel.
    Chaque match terminé est comparé aux notes que les équipes avaient AVANT son
    coup d'envoi (matchs antérieurs uniquement), jamais aux notes actuelles."""
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
    scores_par_ecart = {b[2]: {} for b in STAT_BUCKETS}
    total = 0
    home_total = 0

    for c in codes:
        all_m = await db.matches.find({"competition_code": c}, {"_id": 0}).to_list(2000)
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

    result = {
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
    _stats_cache[ck] = (datetime.now(timezone.utc), result)
    return result


@api_router.get("/bets/simulation")
async def bets_simulation():
    """Simulation de paris sur cotes réelles : P&L par tranche d'écart et au total,
    pour 2 stratégies (Favori, Value), chacune en mise fixe (1 u) et ¼ Kelly plafonné
    (bankroll 100 u, gains réinvestis). Seuls les paris du modèle courant comptent."""
    bets = await db.bets.find({"modele": {"$gte": MODELE_PARIS}}, {"_id": 0}).to_list(5000)
    anciens = await db.bets.count_documents({"modele": {"$not": {"$gte": MODELE_PARIS}}})
    settled = [b for b in bets if b.get("status") in ("won", "lost")]
    pending = [b for b in bets if b.get("status") == "pending"]

    def agg(subset):
        by = {}
        for b in subset:
            by.setdefault(b["tranche"], []).append(b)
        par = [{"tranche": lbl, **simulate(by[lbl])} for _, _, lbl in STAT_BUCKETS if lbl in by]
        return {"total": simulate(subset), "par_ecart": par}

    return {
        "disponible": len(settled) > 0,
        "bankroll_initiale": 100,
        "en_attente": len(pending),
        "paris_anciens_exclus": anciens,
        "regles": "Pari sur l'équipe la mieux notée (1N2), aux vraies cotes du bookmaker "
                  "(France en priorité, sinon bet365/pinnacle). Le P&L se construit au fil des "
                  "matchs joués. Probabilité du modèle = % de victoire du favori observé avant-match "
                  "dans la même tranche d'écart. Value = pari placé seulement quand cette probabilité "
                  "dépasse la probabilité implicite de la cote. Kelly = quart de Kelly, plafonné à 5 % "
                  "de la bankroll courante.",
        "strategies": {"favori": agg(settled),
                       "value": agg([b for b in settled if b.get("is_value")])},
    }


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
