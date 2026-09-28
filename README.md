# FootPulse Analytics Pro

Application web (en français) d'analyse statistique des matchs des championnats européens :
notes sur 100 des équipes et des joueurs, signaux de marché (plus/moins de buts, les deux
équipes marquent…), statistiques de calibration et simulation de paris sur cotes réelles.

Ce n'est **pas** un outil de prédiction certaine : tous les calculs sont déterministes,
fondés uniquement sur des données réelles, et une donnée absente est affichée comme
« Donnée indisponible », jamais inventée. La méthodologie complète est exposée par
`GET /api/scoring/config` et affichée sur la page **Méthodologie**.

## Architecture

```
backend/                   FastAPI + MongoDB (Motor), routes préfixées /api
  server.py                point d'entrée (uvicorn server:app) : app, CORS, planification
  core.py                  configuration (.env), journalisation, connexion MongoDB
  analytics.py             chargement d'un championnat + analyses d'équipes, calibration, cache
  jobs.py                  synchronisations (ingestion puis règlement / prise des paris)
  routers/                 matches.py (matchs, équipes, recherche), players.py, stats.py (stats, paris)
  scoring.py, signals.py   notation des équipes, notes avant-match, signaux (Poisson)
  player_scoring.py, player_form.py   notation et forme récente des joueurs
  betting.py               appariement cotes <-> matchs, Kelly, règlement des paris
  ingest.py, player_ingest.py         ingestion football-data.org, Understat, FotMob
  *_client.py              clients des sources externes
  teamnames.py             normalisation des noms d'équipe entre sources
frontend/                  React (CRA + craco), Tailwind, shadcn/ui, recharts
memory/PRD.md              journal produit : objectifs, décisions, historique des livraisons
```

## Sources de données

| Source | Usage | Clé |
| --- | --- | --- |
| [football-data.org](https://www.football-data.org/) v4 (offre gratuite) | matchs, résultats, classements des 12 compétitions gratuites | `FOOTBALL_DATA_TOKEN` |
| Understat | statistiques joueurs (xG/xA) des 5 grands championnats | aucune |
| FotMob | statistiques joueurs Portugal et Pays-Bas | aucune |
| [The Odds API](https://the-odds-api.com/) (offre gratuite) | cotes 1N2 pour la simulation de paris | `ODDS_API_KEY` (optionnelle) |

Synchronisation automatique (APScheduler, UTC) : rafraîchissement léger des résultats
chaque heure à hh:05 (1 appel API), analyse complète chaque jour à 04:30 (saison,
classements, joueurs, cotes). Les analyses d'équipes sont mises en cache 10 min et
recalculées après chaque synchronisation.

## Configuration

`backend/.env` :

| Variable | Rôle |
| --- | --- |
| `MONGO_URL`, `DB_NAME` | connexion MongoDB (obligatoires) |
| `FOOTBALL_DATA_TOKEN` | jeton football-data.org ; sans lui, aucune donnée n'est chargée |
| `ODDS_API_KEY` | active la prise de paris simulés sur cotes réelles |
| `COMPETITIONS` | codes séparés par des virgules (défaut : les 12 compétitions gratuites) |
| `CORS_ORIGINS` | origines autorisées (défaut `*`) |

`frontend/.env` : `REACT_APP_BACKEND_URL` (URL du backend, sans `/api`).

## Lancer en local

```bash
# Backend (port 8001)
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# Frontend (port 3000)
cd frontend
yarn install
yarn start
```

Au premier démarrage avec un jeton valide et une base vide, l'analyse complète se lance
en arrière-plan (quelques minutes, à cause de la limite de 10 requêtes/min).

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

- `tests/test_unit_models.py` : moteur de notation, calibration, paris, noms d'équipe (hors ligne).
- `tests/test_api_offline.py` : tous les endpoints sur une base MongoDB simulée (hors ligne).
- Les autres fichiers sont des tests d'intégration (marqueur `integration`) qui interrogent
  le backend déployé ; ils sont ignorés tant que `REACT_APP_BACKEND_URL` (variable
  d'environnement ou `/app/frontend/.env`) n'est pas défini.
