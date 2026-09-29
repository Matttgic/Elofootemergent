"""Routes statistiques et simulation de paris (cotes réelles The Odds API —
stratégies Favori & Value), avec les tâches de prise et de règlement des paris."""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter

from analytics import PROB_BUCKETS, bucket_label, comp_data, elo_data, prediction, stats_analytics
from betting import MODELE_PARIS, kelly_fraction, match_fixture, settle_outcome, simulate
from core import db
from odds_client import ODDS_SPORT, fetch_odds

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/stats")
async def stats(code: str | None = None):
    return await stats_analytics(code)


async def snapshot_bets():
    """Fige un pari (cote du favori Elo + probabilités du modèle) pour chaque match à
    venir dont on obtient les vraies cotes. Idempotent (un pari par match) ; un pari
    figé avec un ancien modèle et encore en attente est remplacé."""
    if not os.environ.get("ODDS_API_KEY"):
        return {"ok": False, "raison": "cle_absente"}
    eld = await elo_data()
    created = 0
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
            existing = await db.bets.find_one({"_id": mid}, {"modele": 1})
            if existing and (existing.get("modele") or 0) >= MODELE_PARIS:
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
                "commence_time": fx["commence_time"],
                "snapshot_at": datetime.now(timezone.utc).isoformat(), "status": "pending",
            }, upsert=True)
            created += 1
    logger.info("Paris figés (snapshot) : %s nouveaux", created)
    return {"ok": True, "crees": created}


async def settle_bets():
    """Règle les paris en attente (aucun appel API) : gagné/perdu si le match est
    terminé, annulé (mise remboursée) si le match est annulé ou reporté hors délai."""
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

    def agg(subset):
        by = {}
        for b in subset:
            by.setdefault(b["tranche"], []).append(b)
        par = [{"tranche": lbl, **simulate(by[lbl])} for _, _, lbl in PROB_BUCKETS if lbl in by]
        return {"total": simulate(subset), "par_ecart": par}

    return {
        "disponible": len(settled) > 0,
        "bankroll_initiale": 100,
        "en_attente": len(pending),
        "annules": len(voided),
        "paris_anciens_exclus": anciens,
        "regles": "Pari sur le favori du modèle Elo (1N2), aux vraies cotes du bookmaker "
                  "(France en priorité, sinon bet365/pinnacle). Le P&L se construit au fil des "
                  "matchs joués. Probabilité du modèle = probabilité de victoire du favori selon l'Elo "
                  "avant-match. Value = pari placé seulement quand cette probabilité dépasse la "
                  "probabilité implicite de la cote. Kelly = quart de Kelly, plafonné à 5 % de la "
                  "bankroll courante. Un match annulé ou non joué dans les 72 h suivant l'horaire "
                  "prévu annule le pari (mise remboursée). Détail par tranche de probabilité du favori.",
        "strategies": {"favori": agg(settled),
                       "value": agg([b for b in settled if b.get("is_value")])},
    }
