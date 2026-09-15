# FootPulse Analytics Pro — PRD

## Problème / Objectif
Web app (FR) d'analyse statistique des matchs de football des grands championnats européens.
Objectif : système de notation statistique sur 100 (équipes) pour identifier forme et signaux de marché.
NON un outil de prédiction certaine. Aucune donnée fictive — "Donnée indisponible" si absente.

## Architecture
- **Frontend** : React (CRA/craco) + Tailwind + shadcn/ui + recharts + framer-motion. Thème dark "Tactical Performance Pro" (obsidian/emerald/cyan/gold). Mobile-first.
- **Backend** : FastAPI + Motor (MongoDB). Routes préfixées `/api`.
- **Données** : football-data.org API v4 (offre gratuite, token dans `.env`). Ingestion via APScheduler (cron quotidien 04:10 UTC) + ingestion initiale au démarrage si base vide.
- **Calculs** : moteur déterministe/reproductible (scoring.py, signals.py), aucun LLM.

## Personas
- Passionné de foot / analyste amateur voulant lire rapidement la forme des équipes et des tendances statistiques, surtout sur mobile.

## Source de données (réalité)
football-data.org gratuit : matchs/résultats/classements de 7 ligues (PL, PD, SA, BL1, FL1, PPL, DED).
NON fourni : stats individuelles joueurs, tirs, possession, xG/xA → marqués "Donnée indisponible".
Belgique/Écosse/Turquie non couvertes par l'offre gratuite (omises, extensibles via env COMPETITIONS).

## Algorithme de notation (documenté, /api/scoring/config)
- Fenêtre 10 derniers matchs, décroissance géométrique DECAY=0.85 (récents pondérés).
- Ajustement au niveau de l'adversaire (via classement) pour éviter la surnote contre équipes faibles.
- Global = Forme 40% + Diff. buts 25% + Offensif 17.5% + Défensif 17.5%.
- Offensif = buts/match 55% + régularité 30% + forme off. récente 15%.
- Défensif = encaissés/match 55% + clean sheets 30% + forme déf. récente 15%.
- Scores domicile/extérieur = même calcul filtré par lieu.
- Signaux : Over 2.5/1.5, Under 2.5, BTTS, avantage domicile, clean sheet — avec explication chiffrée + confiance.

## Implémenté
### 2026-09-13 — MVP équipes
- [x] Ingestion réelle (football-data.org, 2364 matchs, 7 ligues) + scheduler quotidien
- [x] Scores équipes /100 (global/off/def/forme/domicile/extérieur) + breakdown transparent
- [x] Accueil (matchs du jour, filtres championnat/date), détail match (radar, avantages, signaux, h2h)
- [x] Classement équipes, page équipe (évolution + historique), recherche, méthodologie
- [x] Tests 13/13 backend

### 2026-09-13 — Ajout statistiques joueurs (Understat)
- [x] Source joueurs : Understat (endpoint AJAX getPlayersStats), 5 ligues (PL/PD/BL1/SA/FL1), 2042 joueurs
- [x] Rapprochement automatique équipes Understat <-> football-data (100% matché, alias pour cas limites)
- [x] Scores joueurs /100 : global, buteur, création, offensif, forme (xGChain) — normalisés /90 min + ajustement au temps de jeu, breakdown transparent
- [x] "Joueurs à surveiller" par équipe dans le détail match ; classement joueurs ; recherche joueurs ; player detail
- [x] PPL/DED joueurs = "Donnée indisponible" (jamais inventé)
- [x] Tests 19/19 backend + flows frontend OK

### 2026-09-13 — Forme récente joueur (vrais derniers matchs)
- [x] Journal match par match via Understat getPlayerMatches ; forme sur les 6 derniers matchs joués, pondération décroissante (récence)
- [x] POST /api/players/form (cache 18h, cap 12) ; GET /api/player/{id} inclut forme_recente
- [x] Cartes "Joueurs à surveiller" affichent "X buts et Y passes sur les N derniers matchs" + barre Forme récente cliquable (breakdown buts+passes / xG+xA)
- [x] Radar de comparaison fiabilisé (outerRadius explicite) ; tests 23/23 backend + frontend OK

## Backlog priorisé
- P2 : Découper server.py en routers (matches/players/stats)
- P2 : Rafraîchir le cache /stats en tâche de fond après chaque ingest
- P2 : Données joueurs Portugal/Pays-Bas si source gratuite ; scores exacts fréquents par écart
- P1 : Cache des analyses par championnat (perf leaderboard toutes ligues)
- P2 : Fiche joueur dédiée (page) avec évolution de forme
- P2 : Données joueurs pour Portugal/Pays-Bas si source gratuite trouvée
- P2 : Ajout championnats (Belgique/Écosse/Turquie) si source dispo
- P2 : Filtre par poste sur le classement joueurs, favoris, thème clair

## Prochaines actions
Voir Next Action Items du récap de finish.
