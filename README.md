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
- Contrôle d'accès serveur (403 pour un collaborateur hors périmètre chef
  de service), pas seulement des liens masqués côté interface
- Journal d'audit sur les créations/modifications sensibles

`flask seed-teams` crée les 5 équipes par défaut du département.

**Reste à construire (phases 2 à 6 du CDC) :** tâches et mises à jour
quotidiennes, activités imprévues, génération des rapports (hebdomadaire
auto le vendredi + export Word), tableaux de bord par rôle avec Chart.js.
