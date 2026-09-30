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
  elo.py                   notes Elo (toutes compétitions, saisons précédentes), forme xG, modèle 1N2
  xg_ingest.py             xG par match (Understat) rattachés aux matchs football-data
  jobs.py                  synchronisations (ingestion puis règlement / prise des paris)
  routers/                 matches.py (matchs, équipes, recherche), players.py, stats.py (stats, paris),
                           cotes.py (page « Cotes »)
  cotes_historiques.py     matchs passés aux cotes Pinnacle voisines (data/cotes_pinnacle.csv.gz)
  scoring.py, signals.py   notation /100 des équipes (forme), signaux (Poisson aligné sur l'Elo)
  player_scoring.py, player_form.py   notation et forme récente des joueurs
  betting.py               appariement cotes <-> matchs, Kelly, règlement des paris
  ingest.py, player_ingest.py         ingestion football-data.org, Understat, FotMob
  *_client.py              clients des sources externes
  teamnames.py             normalisation des noms d'équipe entre sources
  tools/backtest_historique.py   backtest du modèle sur 8 saisons (football-data.co.uk)
  tools/cotes_historiques.py     historique des cotes Pinnacle : construction et test à l'aveugle
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
| [football-data.co.uk](https://www.football-data.co.uk/) | historique des cotes Pinnacle (page Cotes, fichier figé du dépôt) et backtests | aucune |

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

**Classement des méthodes** (mis en avant sur les pages Stats et Méthode) : toutes les
méthodes sur les mêmes 7 144 matchs des 5 grands championnats (2021-22 à 2026-27, xG,
notes et cotes disponibles). Indice de précision : 0 = simples fréquences, 100 = Pinnacle.

| Méthode | Indice | Log-loss | Brier | Réussite |
| --- | --- | --- | --- | --- |
| Cotes Pinnacle à la clôture | 100 | 0,9673 | 0,5750 | 54,3 % |
| Cotes Bet365 avant-match | 98 | 0,9699 | 0,5767 | 53,9 % |
| **Pronostic FootPulse (Elo + xG, site)** | **86** | **0,9824** | **0,5851** | **52,9 %** |
| Elo seul | 77 | 0,9915 | 0,5914 | 52,5 % |
| Note de forme /100 | 49 | 1,0221 | 0,6128 | 49,8 % |
| Simples fréquences | 0 | 1,0739 | 0,6499 | 43,7 % |

Reproduire : `python -m tools.backtest_historique --classement`.

**Pistes testées sans gain** (même échantillon, écart de log-loss avec le modèle du site) :
Elo ramené vers la moyenne en début de saison (0 à +0,0001), probabilité de nul selon le
total de buts ou d'xG récents (−0,0003), écart de jours de repos (0), mélange avec les cotes
Bet365 (0,9704 : mieux que le modèle, moins bien que Bet365 seul, qui contient déjà tout ce
que sait le modèle). Les gains restants demandent des données que le modèle n'a pas encore :
xG des autres championnats, absences et compositions.

Les probabilités 1N2 viennent d'un classement **Elo** (K = 20, avantage du terrain de 60
points, marge de buts prise en compte) calculé sur toutes les compétitions et sur les deux
saisons précédentes (chargées une fois depuis football-data.org), puis d'un modèle
logistique ordonné qui convertit l'écart Elo en probabilités. Sur 13 273 matchs de 8
championnats (2021-22 à 2026-27, chaque saison prédite sans regarder l'avenir) :

| Méthode | Log-loss | Réussite |
| --- | --- | --- |
| Fréquences domicile / nul / extérieur | 1,073 | 43,7 % |
| Ancienne note /100 (tranches d'écart) | 1,038 | 47,8 % |
| **Elo** | **0,990** | **51,8 %** |
| Bet365 avant-match | 0,971 | 53,3 % |
| Pinnacle à la clôture | 0,967 | 53,5 % |

Les bookmakers restent plus précis : parier le favori du modèle aux cotes Bet365 aurait
rendu −4,6 %, les paris « value » (avantage ≥ 5 %) −10 %. Pour reproduire :
`cd backend && python -m tools.backtest_historique` (réseau requis).

**Forme xG** : le modèle ajoute l'écart entre expected goals créés et concédés de chaque
équipe (moyenne à demi-vie de 15 matchs, propre à chaque championnat : une équipe promue
ou reléguée repart sans forme xG), dès que les deux équipes ont au moins 3 matchs avec xG ;
sinon, l'Elo seul s'applique. Sources : Understat pour les 5 grands championnats, FotMob
(Opta) pour le Portugal, les Pays-Bas, le Championship et le Brésil.
Sur 7 800 matchs de ces championnats : log-loss 0,992 → **0,983** (Brier 0,592 → 0,586),
soit 38 % de l'écart avec Pinnacle (0,968) comblé. Reproduire :
`python -m tools.backtest_historique --xg`. Les xG sont rattachés aux matchs à chaque
synchro complète (5 appels Understat ; les 2 saisons précédentes une seule fois).

**xG FotMob** (Championship, Portugal, Pays-Bas ; saisons 2024-25 à 2026-27, 4 241 matchs,
log-loss) :

| Championnats | Elo seul | Elo + xG (site) | Pinnacle |
| --- | --- | --- | --- |
| Les 8 championnats | 0,9879 | **0,9794** | 0,9674 |
| 5 grands (Understat) | 0,9847 | **0,9735** | 0,9611 |
| Championship (FotMob) | 1,0447 | **1,0426** | 1,0318 |
| Primeira Liga (FotMob) | 0,9323 | **0,9279** | 0,9154 |
| Eredivisie (FotMob) | 0,9587 | **0,9506** | 0,9390 |

Sans la forme xG par championnat, les xG du Championship dégradaient les prévisions des
promus en Premier League (8 championnats : 0,9832 au lieu de 0,9794). Reproduire :
`python -m tools.backtest_historique --fotmob` (environ 4 700 fiches de match FotMob la
première fois, puis cache). En production, FotMob est lu à chaque synchro complète : la
liste des matchs de la saison, puis une fiche par match encore sans xG (1 500 au plus par
synchro, le rattrapage des 2 saisons précédentes s'étale sur quelques synchros).

**Stats par écart de notes /100** : la page Stats montre aussi le résultat des matchs
selon l'écart des notes globales que les deux équipes avaient avant le coup d'envoi
(recalculées championnat par championnat et saison par saison, sur les seuls matchs
antérieurs), séparé selon que la mieux notée joue à domicile ou à l'extérieur, la note
ne tenant pas compte du terrain. La fiche d'un match à venir affiche la tranche qui lui
correspond (`GET /api/stats/ecart-notes?domicile=78&exterieur=50`). Sur l'historique
football-data.co.uk (19 085 matchs notés), la mieux notée gagne 37 % des matchs avec un
écart de 0–5 et 70 % au-delà de 40 ; à écart de 0–10, jouer à l'extérieur la fait perdre
plus souvent qu'elle ne gagne.

**La note /100 comme modèle** (même protocole, 11 740 matchs où les deux notes existent) :

| Méthode | Log-loss | Brier | Réussite |
| --- | --- | --- | --- |
| Note /100 seule (écart des notes globales) | 1,0220 | 0,6126 | 49,1 % |
| **Elo seul** | **0,9915** | **0,5916** | **51,7 %** |
| Elo + note /100 | 0,9912 | 0,5915 | 51,8 % |
| Elo + note globale, attaque, défense, forme | 0,9909 | 0,5912 | 52,0 % |
| Pinnacle à la clôture | 0,9697 | 0,5770 | 53,4 % |

Ajouter la note à l'Elo ne gagne que 0,0003 à 0,0006 (du niveau de la marge d'erreur, et
moins bien la dernière saison) ; avec la forme xG, cela dégrade même le modèle (0,9824 →
0,9826). Le modèle reste donc Elo (+ xG). La page Stats compare aussi, sur la saison en
cours, le modèle du site à la note seule. Reproduire :
`python -m tools.backtest_historique --notes`.

**Cotes similaires** (page **Cotes**, `GET /api/cotes/similaires?domicile=1.30&nul=5.75&exterieur=10.5`) :
on entre les cotes 1N2 d'un match (et, si l'on veut, les deux équipes) ; le site retrouve les
matchs passés dont les cotes Pinnacle à la clôture étaient proches (± 5 % par défaut sur
chaque cote, marge du bookmaker retirée) et montre comment ils ont fini, puis les matchs de
chaque équipe à une cote de victoire proche. Le résultat commence par le décompte (N matchs : X victoires
à domicile, Y nuls, Z victoires à l'extérieur) et finit, avec les équipes, par un résumé 1 / N / 2 de
chaque source et une tendance générale (tous ces matchs mis ensemble, chacun compté une fois). Historique : football-data.co.uk, 160 868 matchs
de 38 championnats, mars 2012 à janvier 2026 (le site ne publie plus les cotes Pinnacle
depuis), figé dans `backend/data/cotes_pinnacle.csv.gz` (2,3 Mo, ≈ 30 Mo en mémoire, chargé
en 1 s à la première requête). Un même triplet de cotes se répète rarement (75 % des matchs
n'ont aucun jumeau exact), d'où la tolérance.

Test à l'aveugle (chaque saison jouée avec les seules saisons précédentes, 148 353 matchs de
2013-14 à 2025-26, cotes Pinnacle à la clôture) :

| Idée | Résultat |
| --- | --- |
| Prévoir avec les fréquences des matchs aux cotes voisines | log-loss 1,0030 contre 1,0019 pour la cote seule |
| Parier quand fréquence passée × cote > 1 | 90 364 paris, −3,8 % (parier tout : −4,0 %) |
| … seulement quand l'écart dépasse 5 % | 21 639 paris, −7,0 % |
| Une équipe qui bat ses cotes une saison, la suivante | corrélation +0,009 (6 967 équipes-saisons) |
| Parier une équipe d'après son historique à cote proche | 41 604 paris, −2,4 % |
| Rejouer les tranches de cotes rentables par le passé | 43 056 paris, −1,8 % |
| Combiner cote, cotes voisines et équipes (poids réglés sur le passé) | poids de l'historique : 0 chaque saison |
| Tendance de la page (cotes voisines + équipes, tout mis ensemble) | bonne issue 50,3 % comme la cote seule ; paris −3,8 % |

Les cotes Pinnacle sont presque parfaitement calibrées : l'historique ne dit rien de plus
qu'elles. Seuls les très gros favoris (cote < 1,35) frôlent l'équilibre, les grosses cotes
perdent beaucoup (−11 % à −38 % au-delà de 10). Construire le fichier :
`python -m tools.cotes_historiques --build` (réseau) ; reproduire le test (hors ligne) :
`python -m tools.cotes_historiques` ; recherche en ligne de commande :
`python -m tools.cotes_historiques --cotes 1.30 5.75 10.5 --dom "Paris SG" --ext Marseille`.

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
- `tests/test_cotes.py` : cotes similaires, équipes, fichier de l'historique Pinnacle et routes /api/cotes (hors ligne).
- Les autres fichiers sont des tests d'intégration (marqueur `integration`) qui interrogent
  un backend déployé : ils ne tournent que si `REACT_APP_BACKEND_URL` est défini, par
  exemple `REACT_APP_BACKEND_URL=https://footpulse-api.onrender.com pytest`.
