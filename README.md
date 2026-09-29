# FootPulse Analytics Pro

Application web (en français) d'analyse statistique des matchs des championnats européens :
notes Elo et probabilités victoire / nul / défaite, notes sur 100 des équipes et des joueurs,
signaux de marché (plus/moins de buts, les deux équipes marquent…), qualité du modèle et
simulation de paris sur cotes réelles.

**En ligne : https://footpulses.vercel.app** — API : https://footpulse-api.onrender.com
(`/api/health`, `/api/status`).

Ce n'est **pas** un outil de prédiction certaine : tous les calculs sont déterministes,
fondés uniquement sur des données réelles, et une donnée absente est affichée comme
« Donnée indisponible », jamais inventée. La méthodologie complète est exposée par
`GET /api/scoring/config` et affichée sur la page **Méthodologie**.

## Architecture

```
backend/                   FastAPI + MongoDB (Motor), routes préfixées /api
  server.py                point d'entrée (uvicorn server:app) : app, CORS, planification
  core.py                  configuration (.env), journalisation, connexion MongoDB
  analytics.py             chargement d'un championnat + analyses d'équipes, Elo, stats, cache
  elo.py                   notes Elo (toutes compétitions, saisons précédentes) + modèle 1N2
  jobs.py                  synchronisations (ingestion puis règlement / prise des paris)
  routers/                 matches.py (matchs, équipes, recherche), players.py, stats.py (stats, paris)
  scoring.py, signals.py   notation /100 des équipes (forme), signaux (Poisson aligné sur l'Elo)
  player_scoring.py, player_form.py   notation et forme récente des joueurs
  betting.py               appariement cotes <-> matchs, Kelly, règlement des paris
  ingest.py, player_ingest.py         ingestion football-data.org, Understat, FotMob
  *_client.py              clients des sources externes
  teamnames.py             normalisation des noms d'équipe entre sources
  tools/backtest_historique.py   backtest du modèle sur 8 saisons (football-data.co.uk)
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

Synchronisation automatique (UTC) : rafraîchissement léger des résultats chaque heure à
hh:05 (1 appel API), analyse complète chaque jour à 04:30 (saison, classements, joueurs,
cotes). Elle tourne dans l'API (APScheduler) ou, sur un hébergement qui se met en veille,
dans GitHub Actions via `python -m jobs light|full`. Les analyses d'équipes sont mises en
cache 10 min et recalculées après chaque synchronisation. Filet de sécurité : si la
dernière synchro a plus de 2 h (cron GitHub en retard), l'API lance d'elle-même un
rafraîchissement léger à son réveil ou à la consultation de l'accueil.

## Configuration

`backend/.env` (modèle : `backend/.env.example`, jamais commité) :

| Variable | Rôle |
| --- | --- |
| `MONGO_URL`, `DB_NAME` | connexion MongoDB (obligatoires) |
| `FOOTBALL_DATA_TOKEN` | jeton football-data.org ; sans lui, aucune donnée n'est chargée |
| `ODDS_API_KEY` | active la prise de paris simulés sur cotes réelles |
| `COMPETITIONS` | codes séparés par des virgules (défaut : les 12 compétitions gratuites) |
| `CORS_ORIGINS` | origines autorisées, séparées par des virgules (défaut `*`) |
| `SCHEDULER_ENABLED` | `false` pour couper le planificateur interne (hébergement qui se met en veille) ; le rattrapage léger des données de plus de 2 h reste actif |

`frontend/.env` (modèle : `frontend/.env.example`) : `REACT_APP_BACKEND_URL` (URL du backend, sans `/api`).

## Lancer en local

```bash
# Backend (port 8001) — nécessite un MongoDB local ou Atlas
cd backend
pip install -r requirements.txt
cp .env.example .env   # puis renseigner FOOTBALL_DATA_TOKEN
uvicorn server:app --reload --port 8001

# Frontend (port 3000)
cd frontend
cp .env.example .env
yarn install
yarn start
```

Au premier démarrage avec un jeton valide et une base vide, l'analyse complète se lance
en arrière-plan (quelques minutes, à cause de la limite de 10 requêtes/min).

## Déploiement gratuit (Vercel + Render + MongoDB Atlas + GitHub Actions)

| Élément | Service | Fichier |
| --- | --- | --- |
| Frontend (build React statique) | Vercel, offre Hobby | `frontend/vercel.json` |
| API FastAPI | Render, offre gratuite | `render.yaml` |
| Base de données | MongoDB Atlas, cluster M0 (512 Mo, largement suffisant) | — |
| Synchronisations planifiées | GitHub Actions (minutes illimitées pour un dépôt public) | `.github/workflows/sync.yml` |

### Production actuelle

| Élément | Adresse / réglage |
| --- | --- |
| Site | https://footpulses.vercel.app (Vercel, *Settings > Domains*) |
| API | https://footpulse-api.onrender.com (Render, service `footpulse-api`, région Frankfurt) |
| Base | MongoDB Atlas M0 `Cluster0`, AWS Frankfurt, base `footpulse` |
| Synchros | GitHub Actions `sync.yml` : toutes les heures à hh:05, analyse complète à 04:30 UTC |
| `CORS_ORIGINS` (Render) | `https://footpulses.vercel.app` |

Changer l'adresse du site implique de mettre à jour `CORS_ORIGINS` sur Render (plusieurs
adresses séparées par des virgules), sinon le site s'affiche sans données.

### Mise en place pas à pas

1. **MongoDB Atlas** : créer un cluster M0 (région AWS Frankfurt `eu-central-1`, comme
   l'API Render), un utilisateur de base de données, et autoriser
   l'accès réseau depuis `0.0.0.0/0` (Render et GitHub Actions n'ont pas d'IP fixe).
   Récupérer la chaîne de connexion `mongodb+srv://…`.
2. **Render** : *New > Blueprint*, choisir ce dépôt (`render.yaml` est détecté). Renseigner
   `MONGO_URL`, `FOOTBALL_DATA_TOKEN` et, une fois le frontend en ligne, `CORS_ORIGINS`.
   Noter l'URL de l'API (ici `https://footpulse-api.onrender.com`) ; `/api/health` doit
   répondre `{"ok": true}`.
3. **GitHub** : *Settings > Secrets and variables > Actions*, ajouter les secrets
   `MONGO_URL`, `FOOTBALL_DATA_TOKEN` et, si besoin, `ODDS_API_KEY`. Puis *Actions >
   Synchronisation des données > Run workflow* (mode `full`) pour remplir la base
   (quelques minutes). Ensuite, le workflow tourne seul toutes les heures et à 04:30 UTC.
4. **Vercel** : *Add New > Project*, importer ce dépôt avec **Root Directory** = `frontend`
   et la variable `REACT_APP_BACKEND_URL` = URL Render. Choisir l'adresse du site dans
   *Settings > Domains* (ici `footpulses.vercel.app`), puis la mettre dans `CORS_ORIGINS`
   sur Render.

Limites à connaître : l'API Render gratuite se met en veille après 15 min sans visite
(premier chargement ~30-60 s, signalé sur le site par un bandeau « Réveil du serveur ») ;
les tâches planifiées GitHub peuvent avoir du retard, voire être sautées aux heures
chargées (le rattrapage automatique ci-dessus compense) ; les analyses se rafraîchissent au plus 10 min après
chaque synchronisation (cache de l'API) ; GitHub suspend les workflows planifiés d'un
dépôt sans aucune activité pendant 60 jours (les réactiver dans l'onglet *Actions*).

Pour un serveur toujours allumé (VPS, Railway…), laisser `SCHEDULER_ENABLED=true` : l'API
planifie alors elle-même les synchronisations et le workflow GitHub peut être désactivé.

## Modèle et backtest

Les probabilités 1N2 viennent d'un classement **Elo** (K = 20, avantage du terrain de 60
points, marge de buts prise en compte) calculé sur toutes les compétitions et sur les deux
saisons précédentes (chargées une fois depuis football-data.org), puis d'un modèle
logistique ordonné qui convertit l'écart Elo en probabilités. Sur 13 273 matchs de 8
championnats (2021-22 à 2026-27, chaque saison prédite sans regarder l'avenir) :

| Méthode | Log-loss | Réussite |
| --- | --- | --- |
| Fréquences domicile / nul / extérieur | 1,073 | 43,7 % |
| Ancienne note /100 (tranches d'écart) | 1,038 | 47,8 % |
| **Elo (site)** | **0,990** | **51,8 %** |
| Bet365 avant-match | 0,971 | 53,3 % |
| Pinnacle à la clôture | 0,967 | 53,5 % |

Les bookmakers restent plus précis : parier le favori du modèle aux cotes Bet365 aurait
rendu −4,6 %, les paris « value » (avantage ≥ 5 %) −10 %. Pour reproduire :
`cd backend && python -m tools.backtest_historique` (réseau requis).

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Le workflow GitHub **Tests** (`.github/workflows/tests.yml`) lance automatiquement, sur
chaque PR et chaque push sur `main`, ces tests hors ligne, le build de production du
frontend (avec `CI=true`, comme sur Vercel) et des parcours dans un vrai navigateur.

Tests navigateur (`e2e/`, Playwright) : le site compilé face à une API simulée (données
des tests hors ligne, sans réseau) — accueil, fiche match, fiche équipe, classements,
stats, méthodologie, recherche, comparateur et bandeau de réveil du serveur.

```bash
cd backend && pip install -r requirements-dev.txt
cd ../frontend && REACT_APP_BACKEND_URL=http://127.0.0.1:8765 yarn build
cd ../e2e && npm ci && npx playwright install chromium && npx playwright test
```

- `tests/test_unit_models.py` : Elo et probabilités 1N2, notation, paris, noms d'équipe (hors ligne).
- `tests/test_api_offline.py` : tous les endpoints sur une base MongoDB simulée (hors ligne).
- Les autres fichiers sont des tests d'intégration (marqueur `integration`) qui interrogent
  un backend déployé : ils ne tournent que si `REACT_APP_BACKEND_URL` est défini, par
  exemple `REACT_APP_BACKEND_URL=https://footpulse-api.onrender.com pytest`.
