import click
from flask import Flask

from .extensions import db
from .models import Team, User, UserRole

DEFAULT_TEAMS = [
    "Comptabilité",
    "Contrôle de gestion",
    "Trésorerie",
    "Achat",
    "Stock et Magasin",
]


def register_cli(app: Flask) -> None:
    @app.cli.command("seed-teams")
    def seed_teams() -> None:
        """Crée les équipes par défaut du département (section 3)."""
        created = 0
        for name in DEFAULT_TEAMS:
            if db.session.query(Team).filter_by(name=name).one_or_none():
                continue
            db.session.add(Team(name=name))
            created += 1
        db.session.commit()
        click.echo(f"{created} équipe(s) créée(s).")

    @app.cli.command("seed-admin")
    @click.option("--username", prompt=True)
    @click.option("--first-name", prompt=True)
    @click.option("--last-name", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def seed_admin(username: str, first_name: str, last_name: str, password: str) -> None:
        """Crée le premier compte chef de service."""
        if db.session.query(User).filter_by(username=username).one_or_none():
            click.echo(f"Utilisateur '{username}' existe déjà.")
            return

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.CHEF_SERVICE,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Chef de service '{username}' créé.")

    @app.cli.command("generate-weekly-reports")
    @click.option("--date", "target_date_str", default=None, help="Date de référence (YYYY-MM-DD), par défaut aujourd'hui")
    def generate_weekly_reports_cmd(target_date_str: str | None) -> None:
        """Génère automatiquement les rapports hebdomadaires en brouillon (RB-020, RB-021)."""
        from datetime import datetime
        from .services.report_service import generate_weekly_reports_for_all

        target_date = None
        if target_date_str:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        reports = generate_weekly_reports_for_all(target_date=target_date)
        click.echo(f"Génération terminée : {len(reports)} rapport(s) hebdomadaire(s) généré(s) ou vérifié(s).")

    @app.cli.command("check-deadlines-and-reminders")
    def check_deadlines_cmd() -> None:
        """Vérifie les échéances imminentes, les retards et envoie les rappels de mise à jour (CDC Section 23)."""
        from .services.notification_service import check_deadlines_and_send_reminders
        counts = check_deadlines_and_send_reminders()
        click.echo(
            f"Vérification terminée : {counts['due_soon']} alerte(s) échéance, "
            f"{counts['late']} alerte(s) retard, {counts['update_reminders']} rappel(s) mise à jour."
        )

