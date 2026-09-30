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
- P1 : Cache des analyses par championnat (perf leaderboard toutes ligues)
- P2 : Ajout championnats (Belgique/Écosse/Turquie) si source dispo
- P2 : Journal match par match FotMob pour la forme récente des joueurs PPL/DED
- P2 : Thème clair

### 2026-09-15 — Scores fréquents + recalibration joueurs + FotMob (Portugal/Pays-Bas)
- [x] Stats : scores exacts les plus fréquents par tranche d'écart de notes (vue équipe mieux notée), jusqu'à 4 par tranche, %/n — /api/stats -> par_ecart_note[].scores_frequents + affichage Stats.jsx
- [x] Recalibration des NOTES JOUEURS (buteur/création/offensif) : échelle exigeante score=100×(prod/réf élite)^0.72, ajustement fiabilité (RELIABILITY_MIN=900) appliqué aux sous-scores -> fin des notes gonflées en petit échantillon. Formule des NOTES ÉQUIPE INCHANGÉE (scoring.py non modifié)
- [x] Nouvelle source gratuite FotMob (sans clé) pour joueurs Portugal (PPL) et Pays-Bas (DED) : data.fotmob.com/stats/{lid}/season/{sid}/{stat}.json, saison alignée sur football-data. 819 joueurs (DED 402, PPL 417), 100% rapprochés aux team_id. player_id préfixé "fm". xGChain approximé par xG+xA (documenté)
- [x] fotmob_client.py (nouveau) ; player_ingest.ingest_fotmob_players ; ingest.run_ingest l'appelle ; server.py PLAYER_LEAGUES (Understat ∪ FotMob) pour /match, /leaderboard/players ; get_player_form renvoie None pour ids "fm"
- [x] Tests backend 11/11 (iteration_9.json). Régression Understat OK

## Prochaines actions
Voir Next Action Items du récap de finish.

### 2026-09-23 (2) — Tri par écart, filtre Value, forme FotMob
- [x] Accueil : tri des matchs du jour par écart de notes décroissant (bouton « Trier par écart », data-testid sort-ecart-toggle)
- [x] Filtre + repère « Value » : matchs où favori_gagne_pct ≥ 68 % ET score exact fréquent ≥ 20 % (échantillon ≥ 10). Badge VALUE ambre sur la carte + bouton filtre avec compteur. /api/matches -> calibration.value + calibration.score_frequent
- [x] Forme récente des joueurs FotMob (Portugal/Pays-Bas) : fetch_player_recent (api/data/playerData, sans clé) + compute_fotmob_form (buts+passes 55 % / note de match FotMob 45 %, pondérés récence). get_player_form branche sur FotMob pour les ids « fm »
- [x] Tests full-stack 100% (iteration_10.json : 3 backend + 4 flows frontend)

### 2026-09-23 — Tranches d'écart étendues + repère rapide dans les matchs du jour
- [x] Stats : ajout des tranches 30–35, 35–40, 40–45, 45–50 et 50+ (l'ancienne « 30+ » est remplacée). Tendance monotone confirmée (favori 44% → 92% de victoires selon l'écart)
- [x] Repère rapide sur chaque carte de match (accueil) : écart de notes + favori + barre tricolore (favori/nul/surprise) avec %, via /api/matches -> item.calibration (helper _calibration réutilisant la calibration descriptive). Vérifié desktop + mobile

### 2026-09-28 — Correctifs calibration, paris et robustesse
- [x] /stats sans fuite de données : chaque match terminé est comparé aux notes AVANT-match (matchs antérieurs uniquement, classement reconstitué, ≥ 3 matchs par équipe) — scoring.pre_match_ratings. Sur une ligue aléatoire, le « favori » passait de 55 % V / 19 % D (biaisé) à 37 % / 37 %. Impacte le repère rapide, le badge VALUE et la probabilité du modèle des paris
- [x] Appariement cotes The Odds API ↔ matchs : coup d'envoi à ± 36 h + meilleure similarité domicile+extérieur (fin des confusions Man Utd/Man City, Real Madrid/Real Sociedad, derby retour) — betting.match_fixture
- [x] Kelly : quart de Kelly plafonné à 5 % de la bankroll courante, gains réinvestis, jamais plus que la bankroll engagée sur un même créneau — betting.simulate
- [x] Paris versionnés (modele=2) : les paris figés avant ce correctif sont exclus du bilan (compteur paris_anciens_exclus) et remplacés s'ils sont encore à venir
- [x] POST /api/players/form : ids validés (liste, format Understat/FotMob) et appels externes uniquement pour des joueurs connus en base
- [x] Classements joueurs : plus de boucle de requêtes infinie en cas d'erreur API
- [x] Tests unitaires hors ligne : backend/tests/test_unit_models.py (11 tests)

### 2026-09-28 (2) — Correctifs « moyens » de l'analyse
- [x] Ingestion joueurs (Understat + FotMob) : upsert puis suppression des joueurs absents de la synchro — plus de collection vide pendant le remplacement ; une réponse vide de la source conserve les données existantes (player_ingest._replace_league_players)
- [x] Classement équipes « Tous » : championnats uniquement (coupes exclues) — fin des doublons club/Ligue des champions et du mélange avec les sélections nationales ; les coupes restent consultables via leur filtre
- [x] Paris : un match annulé, attribué sur tapis vert ou non joué dans les 72 h suivant l'horaire prévu annule le pari (statut void, mise remboursée, hors P&L) au lieu de rester « en attente » indéfiniment — betting.settle_outcome ; compteur « annules » sur /api/bets/simulation et la page Stats
- [x] Score défensif : buts encaissés ajustés au niveau de l'adversaire (facteur 1 − 0.25 × force), symétrique de l'offensif. Change légèrement les notes équipe ; texte anti-biais de la méthodologie mis à jour
- [x] Modèle de Poisson (signaux) : moyennes d'équipe ramenées vers la moyenne du championnat (poids = 4 matchs) — plus d'espérances de buts extrêmes sur 2-3 matchs en début de saison
- [x] Tests unitaires : 15 au total (backend/tests/test_unit_models.py)

### 2026-09-28 (3) — Qualité et maintenance
- [x] server.py (≈ 830 lignes) découpé : core.py (config, MongoDB), analytics.py (chargement championnat, analyses, calibration, stats), jobs.py (synchronisations), routers/matches.py, routers/players.py, routers/stats.py (stats + paris). Point d'entrée inchangé (uvicorn server:app). Réponses de l'API vérifiées identiques sur 212 appels, hors ajouts ci-dessous
- [x] Cache des analyses d'équipes par championnat et des stats (10 min, vidé après chaque synchro), verrou par clé, calculs lourds dans un thread : plus de recalcul complet à chaque requête ni de boucle asynchrone bloquée
- [x] Doublons supprimés : calibration de /match (même helper que /matches → ajoute favori_cote, score_frequent, value), document match de l'ingestion complète, normalisation des noms d'équipe (teamnames.py commun)
- [x] Rapprochements d'équipes : suppression de l'alias « Paris » du PSG (captait Paris FC selon l'ordre), alias The Odds API pour « Rennes » et « Inter Milan » — vérifiés sur les 7 championnats
- [x] COMPETITIONS par défaut = les 12 compétitions gratuites (alignement code/production) ; quota de /api/status calculé
- [x] requirements.txt réduit aux 10 dépendances d'exécution (au lieu du pip freeze de 130 paquets) ; outils de test/lint dans requirements-dev.txt
- [x] Tests : URL du backend centralisée (tests/backend_url.py), tests d'intégration marqués `integration` et ignorés sans backend configuré (plus d'URL de préproduction codée en dur), tranches d'écart périmées corrigées ; nouveau tests/test_api_offline.py (tous les endpoints sur MongoDB simulé) — 27 tests hors ligne
- [x] Frontend : nom d'équipe cliquable vers sa fiche dans le détail du match (lien mort « # ») ; légende du classement joueurs (Understat + FotMob)
- [x] README.md rédigé (architecture, sources, configuration, lancement, tests)

### 2026-09-28 (4) — Sortie d'Emergent, déploiement gratuit
- [x] Frontend sans Emergent : suppression du script assets.emergent.sh et de PostHog (enregistrement de session envoyé à ap.emergent.sh) dans index.html, titre/description FootPulse, paquets @emergentbase/* (téléchargés depuis assets.emergent.sh), overlay / visual-edits / sonde de santé dans craco.config.js, identifiants de test du modèle. yarn.lock commité (registre npm public uniquement) ; build de production vérifié avec CI=true
- [x] Fichiers de la plateforme supprimés : .emergent/ (cron vers leur API interne), .gitconfig, test_result.md, test_reports/, tests/ racine vide ; chemins /app/… retirés des tests
- [x] Cible d'hébergement gratuite : frontend Vercel (frontend/vercel.json, réécritures SPA), API Render (render.yaml, SCHEDULER_ENABLED=false), MongoDB Atlas M0, synchronisations GitHub Actions (.github/workflows/sync.yml : hh:05 léger, 04:30 UTC complet, lancement manuel)
- [x] Backend : `python -m jobs light|full` (code de sortie ≠ 0 en cas d'échec), SCHEDULER_ENABLED, création des index partagée, CORS_ORIGINS vide = `*`
- [x] Tests d'intégration opt-in via REACT_APP_BACKEND_URL ; 29 tests hors ligne ; .env.example backend/frontend ; README : guide de déploiement pas à pas

### 2026-09-30 — Cotes similaires (historique Pinnacle)
- [x] Page « Cotes » (/cotes, lien dans le menu et depuis les cotes d'une fiche match) : on entre 1 / N / 2 (+ équipes facultatives) ; matchs passés aux cotes Pinnacle voisines (± 3/5/10/15 % sur chaque cote sans marge) : fréquence réelle ± marge d'erreur, probabilité annoncée, seuil de rentabilité, rendement à la cote saisie, 10 exemples récents ; équipes à cote de victoire voisine (tous terrains)
- [x] Historique figé : football-data.co.uk, 160 868 matchs, 38 championnats, 2012 → janvier 2026 (cotes Pinnacle à la clôture, plus publiées depuis) — backend/data/cotes_pinnacle.csv.gz, stockage en colonnes (≈ 30 Mo), aucune base
- [x] API : GET /api/cotes/similaires (cotes irréalistes, marge > 20 % ou < −5 %, refusées avec explication), /api/cotes/equipes, /api/cotes/calibration
- [x] Test à l'aveugle (tools/cotes_historiques.py) : l'historique n'apporte rien aux cotes (log-loss 1,0030 vs 1,0019) ; paris « historique favorable » −3,8 % à −7 % ; surperformance d'une équipe non reproductible (corrélation 0,009) ; combinaison : poids 0. Affiché sur la page (« Et pour gagner de l'argent ? ») avec la calibration par tranche de cote
- [x] Tests : tests/test_cotes.py (9 tests hors ligne) + parcours Playwright de la page
