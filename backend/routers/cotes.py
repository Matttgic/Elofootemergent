"""Routes « Cotes » : ce qui s'est passé, dans l'historique des cotes Pinnacle
(football-data.co.uk), aux cotes voisines de celles d'un match, et pour une équipe
quand sa cote de victoire était voisine. Aucune base de données : l'historique est
un fichier figé du dépôt (data/cotes_pinnacle.csv.gz), chargé une fois (≈ 1 s)."""
import asyncio
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

import cotes_historiques as ch

router = APIRouter(prefix="/api")
_lock = asyncio.Lock()

# somme des 1/cote : 1 + marge du bookmaker (≈ 1,03 chez Pinnacle, ≈ 1,06-1,10 en France)
MIN_OVERROUND, MAX_OVERROUND = 0.95, 1.2


async def _historique():
    async with _lock:           # un seul chargement, hors de la boucle asynchrone
        h = await asyncio.to_thread(ch.historique)
    if h is None:
        raise HTTPException(503, "Historique des cotes indisponible")
    return h


@lru_cache(maxsize=1)
def _equipes(h):
    return ch.liste_equipes(h)


@lru_cache(maxsize=1)
def _calibration(h):
    return ch.calibration(h)


@router.get("/cotes/similaires")
async def cotes_similaires(
    domicile: float = Query(gt=1, le=1000), nul: float = Query(gt=1, le=1000),
    exterieur: float = Query(gt=1, le=1000), precision: float = Query(ch.PRECISION, ge=1, le=25),
    equipe_domicile: str | None = Query(None, max_length=80),
    equipe_exterieur: str | None = Query(None, max_length=80),
):
    """Matchs passés aux cotes voisines (± precision % sur chaque cote sans marge) et,
    si demandé, matchs des deux équipes à cote de victoire voisine."""
    cotes = (domicile, nul, exterieur)
    overround = sum(1 / c for c in cotes)
    if overround > MAX_OVERROUND:
        raise HTTPException(422, f"Cotes irréalistes : elles donnent une marge de {100 * (overround - 1):.0f} % "
                                 "au bookmaker, qui prend en réalité entre 2 % (Pinnacle) et 12 %. "
                                 "Vérifie les trois cotes du même match chez un même bookmaker.")
    if overround < MIN_OVERROUND:
        raise HTTPException(422, f"Cotes irréalistes : trop hautes pour un même bookmaker (parier les trois issues "
                                 f"rapporterait {100 * (1 / overround - 1):.0f} % à coup sûr). Vérifie les trois cotes.")
    h = await _historique()
    res = await asyncio.to_thread(ch.recherche, h, cotes, precision, equipe_domicile, equipe_exterieur)
    return {**res, "historique": ch.resume(h)}


@router.get("/cotes/equipes")
async def cotes_equipes():
    h = await _historique()
    return {"equipes": await asyncio.to_thread(_equipes, h)}


@router.get("/cotes/calibration")
async def cotes_calibration():
    """Par tranche de cote : probabilité annoncée par Pinnacle, fréquence réelle et
    rendement, plus le test à l'aveugle des stratégies « mêmes cotes »."""
    h = await _historique()
    return {"historique": ch.resume(h), "calibration": await asyncio.to_thread(_calibration, h),
            "test": ch.TEST_HISTORIQUE}
