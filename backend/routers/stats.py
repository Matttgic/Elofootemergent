"""Routes statistiques et simulation de paris (cotes réelles The Odds API —
stratégies Favori & Value), avec les tâches de prise et de règlement des paris."""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from analytics import (PROB_BUCKETS, bucket_label, comp_data, elo_data, note_gap_history, prediction,
                       stats_analytics)
from betting import (MODELE_PARIS, clv_pct, kelly_fraction, match_fixture, settle_outcome,
                     simulate, value_bets, value_pick)
from core import db
from odds_client import ODDS_SPORT, fetch_odds

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/stats")
async def stats(code: str | None = None):
    return await stats_analytics(code)


@router.get("/stats/ecart-notes")
async def note_gap(domicile: int = Query(ge=0, le=100), exterieur: int = Query(ge=0, le=100)):
    """Résultats passés des matchs au même écart de notes /100, l'équipe la mieux notée
    jouant sur le même terrain (null si notes égales ou trop peu de matchs)."""
    return {"historique": await note_gap_history(domicile, exterieur)}


async def snapshot_bets():
    """Fige un pari (cote du favori Elo, issue « value » éventuelle, probabilités du
    modèle) pour chaque match à venir dont on obtient les vraies cotes. Idempotent (un
    pari par match) ; un pari figé avec un ancien modèle et encore en attente est
    remplacé. Pour un pari déjà figé, seules les cotes les plus récentes sont notées
    (valeur de clôture), sans appel supplémentaire."""
    if not os.environ.get("ODDS_API_KEY"):
        return {"ok": False, "raison": "cle_absente"}
    eld = await elo_data()
    created = updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for code, sport in ODDS_SPORT.items():
        try:
            fixtures = await fetch_odds(sport)
        except Exception as e:  # noqa: BLE001
            logger.error("Cotes %s échec: %s", code, e)
            continue
        if not fixtures:
            continue
        comp = await comp_data(code)
        upcoming = [m for m in comp.matches if m.get("status") in ("TIMED", "SCHEDULED", "POSTPONED")]
        for fx in fixtures:
            if not (fx.get("home_odds") and fx.get("away_odds")):
                continue
            m = match_fixture(fx, upcoming)
            if not m:
                continue
            mid = m["match_id"]
            existing = await db.bets.find_one({"_id": mid}, {"modele": 1, "status": 1})
            if existing and (existing.get("modele") or 0) >= MODELE_PARIS:
                if existing.get("status") == "pending":
                    await db.bets.update_one({"_id": mid}, {"$set": {"cotes_recentes": {
                        "domicile": fx["home_odds"], "nul": fx["draw_odds"], "exterieur": fx["away_odds"],
                        "bookmaker": fx["bookmaker"], "at": now}}})
                    updated += 1
                continue
            pred = prediction(eld, m, (m.get("home_team") or {}).get("shortName") or "Domicile",
                              (m.get("away_team") or {}).get("shortName") or "Extérieur")
            if not pred or not pred["fiable"]:
                continue
            fav_side = "home" if pred["favori_cote"] == "domicile" else "away"
            fav_odds = fx["home_odds"] if fav_side == "home" else fx["away_odds"]
            if not fav_odds or fav_odds <= 1:
                continue
            p = pred["favori_pct"] / 100.0
            implied = 1.0 / fav_odds
            await db.bets.replace_one({"_id": mid}, {
                "_id": mid, "modele": MODELE_PARIS,
                "competition_code": code, "ecart": pred["ecart"],
                "tranche": bucket_label(PROB_BUCKETS, pred["favori_pct"]),
                "probas": {"domicile": pred["domicile_pct"], "nul": pred["nul_pct"],
                           "exterieur": pred["exterieur_pct"]},
                "fav_side": fav_side, "fav_nom": pred["favori"], "fav_odds": round(fav_odds, 3),
                "home_odds": fx["home_odds"], "draw_odds": fx["draw_odds"], "away_odds": fx["away_odds"],
                "bookmaker": fx["bookmaker"], "model_prob": round(p, 4), "implied_prob": round(implied, 4),
                "is_value": p > implied, "kelly_f": round(kelly_fraction(p, fav_odds), 4),
                "value": value_pick(pred, fx),
                "commence_time": fx["commence_time"], "snapshot_at": now, "status": "pending",
            }, upsert=True)
            created += 1
    logger.info("Paris figés (snapshot) : %s nouveaux, %s cotes actualisées", created, updated)
    return {"ok": True, "crees": created, "cotes_actualisees": updated}


async def settle_bets():
    """Règle les paris en attente (aucun appel API) : gagné/perdu si le match est
    terminé, annulé (mise remboursée) si le match est annulé ou reporté hors délai."""
    # Paris v3 figés avant l'ajout de l'issue « value » : complétée à partir des cotes et
    # des probabilités enregistrées au moment du pari (aucune information postérieure).
    async for b in db.bets.find({"modele": {"$gte": MODELE_PARIS}, "value": {"$exists": False},
                                 "probas": {"$exists": True}}):
        pred = {f"{issue}_pct": pct for issue, pct in b["probas"].items()}
        await db.bets.update_one({"_id": b["_id"]}, {"$set": {"value": value_pick(pred, b)}})
    pending = await db.bets.find({"status": "pending"}).to_list(2000)
    now = datetime.now(timezone.utc)
    settled = 0
    for bet in pending:
        m = await db.matches.find_one({"match_id": bet["_id"]},
                                      {"_id": 0, "status": 1, "score": 1, "utc_date": 1})
        outcome = settle_outcome(bet, m, now)
        if outcome is None:
            continue
        ft = ((m or {}).get("score") or {}).get("fullTime") or {}
        h, a = ft.get("home"), ft.get("away")
        result = None if outcome == "void" else ("home" if h > a else ("away" if a > h else "draw"))
        await db.bets.update_one({"_id": bet["_id"]},
                                 {"$set": {"status": outcome, "resultat": result,
                                           "settled_at": now.isoformat()}})
        settled += 1
    if settled:
        logger.info("Paris réglés : %s", settled)
    return settled


@router.get("/bets/simulation")
async def bets_simulation():
    """Simulation de paris sur cotes réelles : P&L par tranche d'écart et au total,
    pour 2 stratégies (Favori, Value), chacune en mise fixe (1 u) et ¼ Kelly plafonné
    (bankroll 100 u, gains réinvestis). Seuls les paris du modèle courant comptent."""
    bets = await db.bets.find({"modele": {"$gte": MODELE_PARIS}}, {"_id": 0}).to_list(5000)
    anciens = await db.bets.count_documents({"modele": {"$not": {"$gte": MODELE_PARIS}}})
    settled = [b for b in bets if b.get("status") in ("won", "lost")]
    pending = [b for b in bets if b.get("status") == "pending"]
    voided = [b for b in bets if b.get("status") == "void"]

    def agg(subset, clvs):
        by = {}
        for b in subset:
            by.setdefault(b["tranche"], []).append(b)
        par = [{"tranche": lbl, **simulate(by[lbl])} for _, _, lbl in PROB_BUCKETS if lbl in by]
        clvs = [c for c in clvs if c is not None]
        clv = {"paris": len(clvs),
               "moyenne_pct": round(sum(clvs) / len(clvs), 2) if clvs else None,
               "positifs_pct": round(sum(c > 0 for c in clvs) / len(clvs) * 100, 1) if clvs else None}
        return {"total": simulate(subset), "par_ecart": par, "clv": clv}

    def clv_of(b, issue, odds):
        last = (b.get("cotes_recentes") or {}).get(issue)
        return clv_pct(odds, last)

    fav_issue = {"home": "domicile", "away": "exterieur"}
    fav_clv = [clv_of(b, fav_issue.get(b.get("fav_side")), b.get("fav_odds")) for b in settled]
    val_clv = [clv_of(b, b["value"]["issue"], b["value"]["cote"]) for b in settled if b.get("value")]

    return {
        "disponible": len(settled) > 0,
        "bankroll_initiale": 100,
        "en_attente": len(pending),
        "annules": len(voided),
        "paris_anciens_exclus": anciens,
        "regles": "Pari sur le favori du modèle Elo (1N2), aux vraies cotes du bookmaker "
                  "(France en priorité, sinon bet365/pinnacle). Le P&L se construit au fil des "
                  "matchs joués. Probabilité du modèle = probabilité de victoire du favori selon l'Elo "
                  "avant-match. Value = pari sur l'issue (1, N ou 2) dont l'espérance de gain selon le "
                  "modèle atteint au moins 5 %, s'il y en a une. CLV = cote obtenue comparée à la dernière "
                  "cote relevée avant le match. Kelly = quart de Kelly, plafonné à 5 % de la "
                  "bankroll courante. Un match annulé ou non joué dans les 72 h suivant l'horaire "
                  "prévu annule le pari (mise remboursée). Détail par tranche de probabilité du favori.",
        "strategies": {"favori": agg(settled, fav_clv),
                       "value": agg(value_bets(settled), val_clv)},
    }


@router.get("/bets")
async def bets_list(statut: str = "en_attente", limit: int = 50):
    """Paris suivis (modèle courant) : en attente (prochains d'abord) ou réglés
    (derniers d'abord), avec le match, les issues jouées et la valeur de clôture."""
    pending = statut == "en_attente"
    q = {"modele": {"$gte": MODELE_PARIS},
         "status": "pending" if pending else {"$in": ["won", "lost", "void"]}}
    docs = await db.bets.find(q).sort("commence_time", 1 if pending else -1).to_list(max(1, min(limit, 200)))
    ids = [b["_id"] for b in docs]
    matches = {m["match_id"]: m for m in await db.matches.find(
        {"match_id": {"$in": ids}},
        {"_id": 0, "match_id": 1, "utc_date": 1, "home_team": 1, "away_team": 1, "score.fullTime": 1}).to_list(len(ids) or 1)}
    fav_issue = {"home": "domicile", "away": "exterieur"}
    out = []
    for b in docs:
        m = matches.get(b["_id"]) or {}
        last = b.get("cotes_recentes") or {}
        ft = (m.get("score") or {}).get("fullTime") or {}
        issue = fav_issue.get(b.get("fav_side"))
        v = b.get("value")
        out.append({
            "match_id": b["_id"], "date": m.get("utc_date") or b.get("commence_time"),
            "competition_code": b.get("competition_code"),
            "domicile": {"nom": (m.get("home_team") or {}).get("shortName"), "logo": (m.get("home_team") or {}).get("crest")},
            "exterieur": {"nom": (m.get("away_team") or {}).get("shortName"), "logo": (m.get("away_team") or {}).get("crest")},
            "score": {"home": ft.get("home"), "away": ft.get("away")} if not pending else None,
            "probas": b.get("probas"),
            "favori": {"issue": issue, "nom": b.get("fav_nom"), "cote": b.get("fav_odds"),
                       "proba_pct": round((b.get("model_prob") or 0) * 100, 1),
                       "clv_pct": clv_pct(b.get("fav_odds"), last.get(issue))},
            "value": {**v, "clv_pct": clv_pct(v["cote"], last.get(v["issue"]))} if v else None,
            "bookmaker": b.get("bookmaker"),
            "statut": b.get("status"), "resultat": b.get("resultat"),
        })
    return {"statut": statut, "paris": out}
