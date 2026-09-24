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

**Reste à construire (phases 4 à 6 du CDC) :**
- Phase 4 : Rapports hebdomadaires (génération auto vendredi, édition, soumission, validation, export Word).
- Phase 5 : Tableaux de bord de supervision avancés avec graphiques (Chart.js) et recherche d'historique.
- Phase 6 : Rapport mensuel départemental (consolidation, ajustement, finalisation, export).
