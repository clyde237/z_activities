from enum import Enum


class UserRole(str, Enum):
    """Rôle global de l'utilisateur (section 5).

    Le statut de "chef d'équipe" n'est pas ici : il est porté par
    UserTeam.is_team_lead, car un même utilisateur peut être chef d'équipe
    sur une équipe et simple membre sur une autre (section 3, exemple).
    """

    CHEF_SERVICE = "chef_service"
    COLLABORATEUR = "collaborateur"


class TaskType(str, Enum):
    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"


class TaskPriority(str, Enum):
    BASSE = "basse"
    NORMALE = "normale"
    HAUTE = "haute"
    URGENTE = "urgente"


class TaskStatus(str, Enum):
    """Statuts fonctionnels (section 10).

    "En retard" n'apparaît pas ici : c'est un indicateur calculé à partir
    de due_date, pas un statut stocké (Task.is_late).
    """

    A_FAIRE = "a_faire"
    EN_COURS = "en_cours"
    A_VALIDER = "a_valider"
    TERMINEE = "terminee"
    BLOQUEE = "bloquee"
    REPORTEE = "reportee"
    ANNULEE = "annulee"


class WeeklyReportStatus(str, Enum):
    BROUILLON = "brouillon"
    SOUMIS = "soumis"
    VALIDE = "valide"


class MonthlyReportStatus(str, Enum):
    BROUILLON = "brouillon"
    FINALISE = "finalise"


class PeriodType(str, Enum):
    JOUR = "jour"
    SEMAINE = "semaine"
    MOIS = "mois"
    PERIODE_COMPTABLE = "periode_comptable"
