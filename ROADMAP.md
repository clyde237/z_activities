# Feuille de route — Suivi des activités du département

Dernière revue : 30 septembre 2026

## Objectif du produit

Permettre au chef de service de suivre le travail du département, de superviser les équipes et les collaborateurs, de recueillir un rapport d'activités hebdomadaire par membre et de produire un rapport mensuel consolidé du département.

Ce document décrit l'état observé dans le code et les tests du dépôt. « Implémenté » signifie que le parcours existe; cela ne signifie pas que chaque règle métier a été validée par les utilisateurs ni que le système est prêt pour une exploitation planifiée en production.

## Résumé d'avancement

| Domaine | État | Résumé |
|---|---|---|
| Comptes, rôles et équipes | Implémenté | Gestion des utilisateurs, équipes, affectations et chefs d'équipe. |
| Tâches et suivi quotidien | Implémenté | Affectation, avancement, statuts, historique des mises à jour et retards. |
| Activités imprévues | Implémenté | Déclaration, consultation, édition et supervision. |
| Rapport hebdomadaire individuel | Implémenté | Agrégation, rédaction, soumission, validation, révision et export Word. |
| Rapport mensuel départemental | Implémenté | Consolidation, ajustement rédactionnel, finalisation, réouverture et export Word. |
| Supervision, historique et audit | Implémenté | Vues selon le rôle, recherche transversale et journal d'audit. |
| Notifications | Fonctionnel, automatisation à terminer | Les événements sont notifiés; les vérifications récurrentes sont des commandes manuelles. |
| Exploitation et règles de consolidation | À cadrer/fiabiliser | Planification, règles métier, confidentialité mensuelle et préparation production. |
| Tâches récurrentes et paramètres | Non implémenté | Des bases existent, mais pas les parcours utilisateurs correspondants. |

## Déjà implémenté

### Utilisateurs, rôles et équipes

- Connexion/déconnexion et accès authentifié.
- Rôles chef de service, chef d'équipe et collaborateur, avec contrôles d'accès côté serveur.
- Création et édition de comptes, activation/désactivation, changement de rôle et réinitialisation manuelle du mot de passe par un administrateur.
- Création d'équipes, affectation d'un membre à plusieurs équipes et désignation d'un chef par équipe.
- Référence : [app/routes/users.py](app/routes/users.py), [app/routes/teams.py](app/routes/teams.py), [app/permissions.py](app/permissions.py).

### Travail et activités

- Création et affectation de tâches aux équipes, avec un responsable et un co-responsable optionnel.
- Tâches qualitatives et quantitatives; avancement quantitatif calculé et transitions de statut contrôlées.
- Mise à jour quotidienne avec travail effectué, difficultés et prochaine étape; historique conservé.
- Détection des tâches en retard et déclaration/suivi d'activités imprévues.
- Calendrier, filtres de tâches, pages de détail et indicateurs sur les tableaux de bord.
- Références : [app/services/task_service.py](app/services/task_service.py), [app/services/activity_service.py](app/services/activity_service.py), [app/routes/calendar.py](app/routes/calendar.py).

### Rapports hebdomadaires par membre

- Création idempotente d'un brouillon individuel pour une semaine lundi-dimanche; génération pour les comptes actifs via service, commande CLI et action du chef de service.
- Agrégation des tâches pertinentes, mises à jour et activités imprévues; sections narratives modifiables par l'auteur.
- Cycle brouillon → soumis → validé, avec retour en brouillon pour révision.
- Consultation selon le rôle, aperçu et export Word.
- Références : [app/services/report_service.py](app/services/report_service.py), [app/routes/reports.py](app/routes/reports.py), [app/models/report.py](app/models/report.py).

### Rapport mensuel global

- Création d'un rapport par mois et rattachement des rapports hebdomadaires concernés.
- Consolidation des tâches, activités imprévues, rapports hebdomadaires, équipes et collaborateurs actifs.
- Sections rédactionnelles du chef de service, finalisation/réouverture, export Word.
- Références : [app/services/monthly_report_service.py](app/services/monthly_report_service.py), [app/routes/monthly_reports.py](app/routes/monthly_reports.py).

### Supervision et traçabilité

- Tableaux de bord différenciés pour le chef de service et les chefs d'équipe.
- Recherche transversale dans les tâches, mises à jour, activités et rapports.
- Journal d'audit des opérations sensibles, consultable par le chef de service.
- Références : [app/services/history_service.py](app/services/history_service.py), [app/services/audit_service.py](app/services/audit_service.py), [app/routes/audit.py](app/routes/audit.py).

### Notifications

- Notifications in-app pour attributions de tâches, soumission/validation/révision de rapports, activités imprévues et finalisation mensuelle.
- Commande de vérification des échéances et rappels quotidiens de mise à jour.
- Centre de notifications, marquage comme lu et compteur non lu.
- Références : [app/services/notification_service.py](app/services/notification_service.py), [app/cli.py](app/cli.py), [app/routes/notifications.py](app/routes/notifications.py).

## Partiellement fait ou à fiabiliser

1. **Automatisation périodique** — la génération hebdomadaire et les rappels sont implémentés comme commandes CLI, mais aucun ordonnanceur n'est configuré dans l'application. Les exécuter automatiquement chaque semaine/jour dépend donc encore de l'environnement d'hébergement.
2. **Règles de consolidation** — le calcul des rapports est en place, mais les critères exacts d'inclusion des tâches, le traitement des semaines qui chevauchent deux mois, les doubles responsabilités et la stabilité d'un rapport historique après modification ultérieure des tâches doivent être confirmés avec le métier et couverts par des tests de cas limites.
3. **Visibilité du rapport mensuel** — les tests actuels autorisent tout utilisateur connecté à consulter la liste, le détail et l'export; seules la génération et les modifications sont réservées au chef de service. Confirmer que cette diffusion globale est bien la règle attendue.
4. **Notifications récurrentes** — les alertes sont dédupliquées tant qu'une notification équivalente reste non lue; la fréquence souhaitée et le comportement après lecture doivent être validés en usage réel.
5. **Paramètres** — `/settings` affiche une page et accepte un POST, mais le POST ne persiste pas de configuration métier. Ce n'est pas encore une gestion de paramètres.
6. **Documentation d'avancement** — le README déclare les phases 1 à 7 terminées et 65 tests réussis; lors de cette revue, `pytest -q` a exécuté **69 tests avec succès**. Mettre à jour cette déclaration lorsque le statut produit sera confirmé.

## À développer, par priorité

### P0 — Faire valider le fonctionnement attendu

Obtenir du chef de service les décisions suivantes avant d'automatiser ou de figer les indicateurs :

- Quel jour et quelle heure le rapport hebdomadaire doit-il être disponible et quelle est la date limite de soumission ?
- Le rapport attendu couvre-t-il strictement lundi-dimanche ? Que faire des absences, comptes inactifs et membres affectés à plusieurs équipes ?
- Quelles tâches comptent dans un rapport hebdomadaire/mensuel (création, échéance, activité, statut à la date considérée) ?
- Comment répartir une semaine qui chevauche deux mois ? Faut-il inclure tout le rapport hebdomadaire ou ventiler ses données ?
- Les rapports mensuels et exports sont-ils visibles par tous les collaborateurs, les chefs d'équipe de leur périmètre, ou uniquement le chef de service ?
- Quelles rubriques et quels indicateurs sont obligatoires pour considérer un rapport soumis ou finalisé ?

**Sortie attendue :** règles écrites et approuvées, exemples de rapports conformes et définition des droits de lecture.

### P1 — Verrouiller les chiffres des rapports

- Transformer les décisions métier en règles explicites des services hebdomadaire et mensuel.
- Ajouter des tests sur les frontières de semaine/mois, les tâches chevauchant une période, les changements de statut après clôture, les comptes inactifs, les équipes multiples et le co-responsable.
- Décider si les rapports sont des instantanés au moment de leur génération/soumission ou des vues recalculées sur l'état courant; implémenter et tester le choix.
- Vérifier que les indicateurs de couverture rendent visibles les rapports manquants, brouillons, soumis et validés par personne et période.

**Sortie attendue :** exemples chiffrés validés par le métier et tests déterministes couvrant les cas limites.

### P2 — Planifier les traitements automatiques

- Configurer dans l'environnement de déploiement l'exécution périodique de `generate-weekly-reports` et `check-deadlines-and-reminders`.
- Définir horaires, fuseau, relance après échec et journalisation des exécutions.
- Vérifier qu'une nouvelle exécution ne crée ni rapports ni notifications en double.

**Sortie attendue :** preuve d'une exécution planifiée, journal consultable et procédure de reprise documentée.

### P3 — Valider confidentialité et parcours utilisateur

- Faire approuver la matrice des droits de lecture/édition des rapports mensuels et appliquer les règles sur les pages détail et export, pas seulement dans l'interface.
- Faire un parcours de recette complet : membre saisit et soumet, chef de service relit/renvoie/valide, puis produit le rapport global du mois.
- Vérifier la compréhension des statuts, des retards, des notifications et des exports avec des utilisateurs représentatifs.

**Sortie attendue :** matrice de droits testée et recette métier signée.

### P4 — Préparer l'exploitation

- Définir sauvegarde/restauration de la base, configuration des secrets, déploiement des migrations et procédure de mise à jour.
- Tester les exports Word avec des données représentatives et vérifier lisibilité, signatures et présentation après ouverture dans Word/LibreOffice.
- Documenter les responsabilités d'administration et la procédure de création du premier compte.

**Sortie attendue :** installation reproductible, restauration vérifiée et checklist d'exploitation.

### P5 — Extensions à confirmer

- **Tâches récurrentes :** `AccountingPeriod` existe, mais son commentaire indique que la préparation des tâches récurrentes n'est pas implémentée. À construire seulement si le département veut générer des tâches périodiques à partir des périodes comptables.
- **Paramètres configurables :** horaires, règles de rappel ou modèles de rapport; à préciser si l'équipe doit pouvoir les modifier depuis l'interface.
- Autres exports ou indicateurs additionnels : à prioriser après retour d'usage, pas avant la stabilisation des rapports principaux.

## Tests et éléments de preuve

Les tests couvrent les comptes/équipes, tâches, mises à jour, activités imprévues, rapports hebdomadaires et mensuels, exports Word, notifications, supervision, historique et audit. Vérification effectuée pendant cette revue :

```text
./.venv/bin/pytest -q
69 passed
```

Cette réussite confirme que les tests présents passent; elle ne remplace pas la recette métier, la configuration d'un ordonnanceur ou une validation en environnement de production.

## Prochaine étape recommandée

Organiser une courte validation métier du P0 avec le chef de service. Une fois les règles de consolidation et de visibilité écrites, prendre P1 comme prochain chantier technique, puis planifier P2 avec la personne responsable de l'hébergement.