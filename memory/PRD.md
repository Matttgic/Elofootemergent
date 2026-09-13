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

## Implémenté (2026-09-13)
- [x] Ingestion réelle (2364 matchs, 7 ligues) + scheduler quotidien
- [x] Scores équipes /100 (global/off/def/forme/domicile/extérieur) + breakdown transparent
- [x] Page d'accueil : matchs du jour, filtres championnat/date, cartes de match
- [x] Page détail match : comparaison, radar, avantages, signaux marché, h2h, joueurs (indisponible)
- [x] Modale de décomposition des scores (transparence)
- [x] Classements équipes ; classement joueurs (indisponible)
- [x] Page équipe : stats, graphique d'évolution, historique
- [x] Recherche équipe ; page méthodologie
- [x] Tests : 13/13 backend pytest, flows frontend OK

## Backlog priorisé
- P1 : Source complémentaire gratuite pour données joueurs (ex: scraping FBref/understat légal) afin d'activer scores joueurs & "joueurs à surveiller"
- P1 : Cache des analyses par championnat (perf leaderboard toutes ligues)
- P2 : Ajout de championnats (Belgique/Écosse/Turquie) si source dispo
- P2 : Bascule thème clair, favoris/équipes suivies
- P2 : Filtre statut (à venir / terminés) sur l'accueil

## Prochaines actions
Voir Next Action Items du récap de finish.
