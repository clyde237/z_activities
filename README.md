# Plateforme de suivi des activités — Comptabilité & Finance

Application Flask monolithique (SQLAlchemy + SQLite) pour le suivi des tâches,
mises à jour quotidiennes, activités imprévues et rapports du département
Comptabilité & Finance. Voir le cahier des charges dans le dépôt parent.

## Prérequis

- Python 3.11 ou plus récent
- `venv` disponible dans l'installation Python

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Base de données

Les migrations sont gérées par Flask-Migrate (Alembic) — le schéma n'est
jamais créé implicitement au démarrage.

```bash
export FLASK_APP=run.py
flask db upgrade          # applique les migrations existantes
```

Après une modification de modèle :

```bash
flask db migrate -m "description du changement"
flask db upgrade
```

Créer le premier compte (chef de service) :

```bash
flask seed-admin
```

## Lancement

```bash
flask --app run.py --debug run
```

L'application est disponible sur `http://127.0.0.1:5000`.

## Tests

```bash
pytest
```

## Structure

```text
.
├── app/
│   ├── __init__.py       # Factory Flask
│   ├── cli.py            # Commandes flask (ex: seed-admin)
│   ├── config.py         # Configuration
│   ├── extensions.py     # SQLAlchemy, Flask-Migrate, Flask-Login
│   ├── permissions.py    # Règles d'autorisation par rôle / équipe
│   ├── models/           # User, Team, Task, TaskUpdate, rapports, audit...
│   ├── routes/
│   │   ├── auth.py       # Connexion / déconnexion
│   │   ├── dashboard.py  # Page d'accueil authentifiée
│   │   └── health.py     # Endpoint de santé
│   └── templates/
├── instance/              # Données locales SQLite, non versionnées
├── migrations/             # Migrations Alembic versionnées
├── tests/
├── .env.example
├── requirements.txt
└── run.py
```

## État d'avancement

**Phase 1 (connexion, rôles, utilisateurs, équipes, affectations) terminée :**
- Connexion / déconnexion (Flask-Login), CSRF sur tous les formulaires
- Gestion des utilisateurs (création, modification, rôle, statut actif/inactif)
- Gestion des équipes (création, modification)
- Affectation d'un utilisateur à plusieurs équipes, désignation par équipe
  d'un chef d'équipe (`UserTeam.is_team_lead`)
- Consultation des équipes et membres supervisés sur le tableau de bord (chef d'équipe et collaborateur)
- Visualisation de la composition de chaque équipe (membres et chefs désignés)
- Contrôle d'accès serveur (403 pour un collaborateur hors périmètre chef
  de service), avec pages d'erreur dédiées (403, 404)
- Journal d'audit sur les créations/modifications sensibles

`flask seed-teams` crée les 5 équipes par défaut du département.

**Phase 2 (Gestion des tâches) terminée :**
- Planification et création de tâches par le Chef de service et les Chefs d'équipe (RB-004)
- Affectation à un membre de l'équipe et co-responsable optionnel (RB-006, RB-007)
- Tâches quantitatives avec calcul automatique de progression (RB-010, RB-011)
- Tâches qualitatives avec saisie manuelle de progression (RB-012)
- Cycle de vie et transitions de statuts contrôlées (`ALLOWED_STATUS_TRANSITIONS`)
- Détection et signalement automatique des retards d'échéance (RB-015)
- Protection des informations structurantes réservée à l'encadrement (RB-013)
- Interface de gestion avec filtres (Toutes, Mes tâches, En retard, par équipe et statut)
- Vue détaillée d'une tâche et intégration des indicateurs au tableau de bord (CDC 18, 19, 20)
- Traçabilité complète des créations et modifications dans `audit_logs` (RB-028)

**Phase 3 (Suivi quotidien et activités imprévues) terminée :**
- Mises à jour quotidiennes de tâches avec travail effectué, difficultés, prochaine étape (CDC Section 11, RB-008, RB-009)
- Recalcul automatique de progression pour les tâches quantitatives lors de la mise à jour
- Passage automatique de « À faire » à « En cours » lors de la première mise à jour (RB-014)
- Historique chronologique conservé sans écrasement (section 11)
- Indicateur de mise à jour du jour et bandeau d'alerte/rappel sur le tableau de bord (CDC 11 & 12)
- Déclaration et suivi des activités imprévues par tout collaborateur (RB-005, RB-019)
- Avis / Commentaire de supervision de l'encadrement sur les activités imprévues
- Traçabilité complète de chaque mise à jour et activité imprévue dans `audit_logs` (RB-028)

**Phase 4 (Rapports hebdomadaires et export Word) terminée :**
- Génération automatique des rapports le vendredi pour tous les membres actifs (RB-020, commande `flask generate-weekly-reports`)
- Création initiale en brouillon `BROUILLON` (RB-021)
- Agrégation complète des activités de la semaine (tâches actives, terminées, en cours, en retard, activités imprévues, mises à jour, taux d'avancement)
- Édition libre des synthèses narratives, difficultés, solutions et observations par le collaborateur avant soumission (RB-022)
- Soumission du rapport par le membre au chef de service (`SOUMIS`)
- Validation finale réservée exclusivement au Chef de service (`VALIDE`, RB-023) ou demande de révision (retour en `BROUILLON`)
- Périmètre de consultation respecté : le chef d'équipe consulte les rapports des membres de ses équipes (RB-024)
- Export natif du rapport au format Microsoft Word (`.docx`) conforme aux normes de la section 16 du CDC (en-tête Zingana, tables stylisées, signatures)
- Intégration sur le tableau de bord des alertes de validation et du statut du rapport de la semaine courante
- Traçabilité intégrale dans le journal d'audit (`audit_logs`)

**Phase 5 (Supervision, Dashboards avancés, Historique transversal et Audit) terminée :**
- Tableaux de bord de supervision adaptés par rôle pour le Chef de service et les Chefs d'équipe (CDC Sections 18 et 19)
- Visualisations graphiques interactives intégrées avec Chart.js :
  - Graphique circulaire (Doughnut) de répartition des tâches par statut
  - Graphique en barres (Bar chart) d'avancement moyen par équipe
- Supervision détaillée et consolidée par équipe : avancement global, tâches en cours, terminées, retards
- Supervision individuelle des collaborateurs : suivi des tâches en cours, retards, taux d'avancement moyen, état du suivi quotidien du jour et statut du rapport hebdomadaire
- Moteur de recherche et d'historique transversal multi-critères (CDC Section 21, RB-030) :
  - Filtre textuel plein texte (titre, description, difficultés, résultats)
  - Filtres par collaborateur, équipe supervisée, période de dates et type d'entité (tâches, mises à jour, imprévues, rapports)
  - Périmètre de visibilité rigoureusement cloisonné selon le rôle de l'utilisateur
- Interface de consultation et de filtrage du journal d'audit (`/audit`) réservée au Chef de service (CDC Section 22, RB-028) : filtres par auteur, action, type d'entité et dates

**Phase 6 (Rapport mensuel départemental, consolidation, ajustement et export Word) terminée :**
- Modèle de données et cycle de vie du rapport mensuel (`MonthlyReport`, `MonthlyReportStatus`: `BROUILLON`, `FINALISE`) (CDC Sections 17 & 28, RB-025)
- Consolidation automatique et agrégation globale à partir des données réelles et rapports hebdos (RB-026) :
  - Métriques départementales globales (volume des tâches, taux d'avancement moyen, retards, imprévus, couverture hebdos)
  - Performance et indicateurs consolidés par équipe
  - Suivi individuel des collaborateurs du département
  - Tâches majeures et projets structurants du mois
  - Activités imprévues et urgences traitées
  - Synthèse des difficultés récurrentes et solutions issues des rapports hebdomadaires
- Workflow d'ajustement rédactionnel sous l'autorité du Chef de service (CDC Section 17 & 28, RB-027) :
  - Synthèse générale départementale (`narrative_summary`)
  - Faits marquants et réalisations majeures (`key_achievements`)
  - Difficultés consolidées d'encadrement (`difficulties_summary`)
  - Perspectives et plan d'action pour le mois prochain (`action_plan`)
  - Recommandations et observations de la Direction du Service (`observations`)
- Finalisation officielle et possibilité de réouverture contrôlée pour correctif
- Export Word natif au format `.docx` (CDC Section 29) : en-tête officiel de l'Hôtel Le Zingana, tableaux stylisés aux normes graphiques de l'établissement, bilans par équipe, blocs de visas et signatures (Chef de service, Direction Financière, Direction Générale)
- Intégration complète à la recherche dans l'historique transversal et traçabilité inaltérable dans le journal d'audit (`audit_logs`)

---

### Bilan de mise en conformité avec le Cahier des Charges

L'ensemble des **6 phases du MVP (Phases 1 à 6)** spécifiées dans le Cahier des Charges fonctionnel est désormais **100% implémenté, testé (59 tests unitaires et d'intégration automatisés réussis) et validé**.


