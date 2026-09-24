from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

auth_blueprint = Blueprint("auth", __name__)


@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.session.query(User).filter_by(username=username).one_or_none()

        if user is None or not user.check_password(password) or not user.is_active_account:
            flash("Identifiant ou mot de passe incorrect.", "error")
            return render_template("auth/login.html"), 401

        login_user(user)
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html")


@auth_blueprint.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
