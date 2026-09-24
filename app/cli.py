import click
from flask import Flask

from .extensions import db
from .models import User, UserRole


def register_cli(app: Flask) -> None:
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
