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
